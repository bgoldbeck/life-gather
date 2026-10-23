import asyncio
import json
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from lifegather.chat.claude import ClaudeProvider
from lifegather.chat.provider import Answer, OpenAIProvider
from lifegather.chat.streaming import AnswerPreview, DeltaSink

pytestmark = pytest.mark.usefixtures("configured_database")


def test_openai_stream_delivers_json_deltas_before_completion() -> None:
    raw = json.dumps({"text": "Synthetic answer", "source_ids": ["source"]})
    response = {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": raw}]}
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    events: list[dict[str, Any]] = [
        {"type": "response.output_text.delta", "delta": raw[:20]},
        {"type": "response.output_text.delta", "delta": raw[20:]},
        {"type": "response.completed", "response": response},
    ]
    seen: list[str] = []
    completed = False

    async def sink(text: str) -> None:
        assert not completed
        seen.append(text)

    class Wire(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            nonlocal completed
            for event in events:
                if event["type"] == "response.completed":
                    completed = True
                for byte in ("data: " + json.dumps(event) + "\n\n").encode():
                    yield bytes([byte])

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx2.Response(
            200,
            stream=Wire(),
            headers={"content-type": "text/event-stream"},
        )

    result = asyncio.run(
        OpenAIProvider(httpx2.MockTransport(handle)).stream_complete(
            "synthetic", "model", "instruction", {}, Answer, sink
        )
    )
    assert "".join(seen) == raw
    assert result.value["text"] == "Synthetic answer"


def test_claude_stream_and_partial_json_escape_boundaries() -> None:
    raw = json.dumps({"text": 'Synthetic "quoted" answer 🌿', "source_ids": ["source"]})
    events: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {"type": "message", "usage": {"input_tokens": 10}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        *[
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": part},
            }
            for part in raw
        ],
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    ]
    seen: list[str] = []

    async def sink(text: str) -> None:
        seen.append(text)

    preview = AnswerPreview(sink)

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx2.Response(
            200,
            content="".join(
                "data: " + json.dumps(event) + "\r\n\r\n" for event in events
            ),
        )

    result = asyncio.run(
        ClaudeProvider(httpx2.MockTransport(handle)).stream_complete(
            "synthetic", "model", "instruction", {}, Answer, preview.append
        )
    )
    assert len(seen) > 2
    assert "".join(seen) == result.value["text"]
    assert result.input_tokens == 10 and result.output_tokens == 5


def test_stream_without_terminal_event_is_rejected_and_redacted() -> None:
    from lifegather.chat.provider import ProviderError

    async def sink(text: str) -> None:
        pass

    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            content='data: {"type":"response.output_text.delta","delta":"private"}\n\n',
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(
            OpenAIProvider(httpx2.MockTransport(handle)).stream_complete(
                "synthetic", "model", "instruction", {}, Answer, sink
            )
        )
    assert "private" not in str(error.value)


def test_stream_route_preserves_citations_history_and_retry_identity() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from fastapi.testclient import TestClient
    from test_chat import FakeProvider

    from lifegather.chat.provider import Completion
    from lifegather.main import create_app
    from lifegather.memory.schemas import SourceInput
    from lifegather.memory.service import MemoryService

    class StreamingFake(FakeProvider):
        waiting = False
        entered = threading.Event()

        async def stream_complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: type[BaseModel],
            emit: DeltaSink,
        ) -> Completion:
            result = await self.complete(secret, model, instruction, payload, schema)
            raw = json.dumps(result.value)
            await emit(raw[:35])
            self.entered.set()
            while self.waiting:
                await asyncio.sleep(0.01)
            await emit(raw[35:])
            return Completion(result.value, 20, 10)

    app = create_app()
    with TestClient(app) as client:
        store = app.state.auth_store
        signed = store.login(
            "stream-user", "stream@example.test", "Stream", now=2000000000
        )
        client.cookies.set("lifegather_session", signed.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        fake = StreamingFake()
        app.state.chat_provider = fake
        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(signed.user, "ai", "openai", "Synthetic", "synthetic")
        vault.set_preferences(signed.user, True)
        MemoryService(store.engine).ingest(
            signed.user, SourceInput(text="Synthetic filter 16x25x1")
        )
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        url = f"/api/chat/conversations/{conversation}/stream"
        body = {
            "request_id": "stream-1",
            "mode": "ask",
            "text": "filter?",
            "credential_id": credential.id,
            "model": "synthetic",
        }
        assert client.post(url, json=body).status_code == 403
        response = client.post(url, json=body, headers=headers)
        frames = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert any(frame["type"] == "draft" for frame in frames)
        assert frames[-1]["turn"]["state"] == "complete"
        calls = len(fake.calls)
        client.post(url, json=body, headers=headers)
        assert len(fake.calls) == calls
        fake.bad_citation = True
        failed = client.post(
            url, json={**body, "request_id": "stream-2"}, headers=headers
        )
        final = json.loads(
            [
                line[6:]
                for line in failed.text.splitlines()
                if line.startswith("data: ")
            ][-1]
        )
        assert final["turn"]["state"] == "failed"
        assert "16x25x1" not in final["turn"]["result"]["text"]
        fake.bad_citation = False
        fake.waiting = True
        fake.entered.clear()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.post,
                url,
                json={**body, "request_id": "stream-cancel"},
                headers=headers,
            )
            try:
                assert fake.entered.wait(3)
                canceled = client.post(
                    "/api/chat/requests/stream-cancel/cancel", headers=headers
                )
                assert canceled.json()["state"] == "canceled"
                stopped = pending.result(timeout=5)
                terminal = json.loads(
                    [
                        line[6:]
                        for line in stopped.text.splitlines()
                        if line.startswith("data: ")
                    ][-1]
                )
                assert terminal["turn"]["state"] == "canceled"
            finally:
                fake.waiting = False
