import asyncio
import json
from typing import Any

import httpx2
import pytest

from lifegather.chat.google import GeminiProvider
from lifegather.chat.provider import Answer, ProviderError, SearchPlan

pytestmark = pytest.mark.usefixtures("configured_database")


def interaction(text: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": text}]}
        ],
        "usage": {
            "total_input_tokens": 10,
            "total_output_tokens": 5,
            "total_thought_tokens": 2,
        },
    }


def test_google_uses_stateless_fixed_endpoint_and_private_header() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        assert (
            str(request.url)
            == "https://generativelanguage.googleapis.com/v1beta/interactions"
        )
        assert request.headers["x-goog-api-key"] == "synthetic-only"
        body = json.loads(request.content)
        assert body["store"] is False and body["background"] is False
        assert body["tools"] == []
        assert body["generation_config"]["max_output_tokens"] == 1500
        assert body["response_format"]["mime_type"] == "application/json"
        assert body["input"][1]["type"] == "image"
        return httpx2.Response(200, json=interaction('{"query":"filter"}'))

    result = asyncio.run(
        GeminiProvider(httpx2.MockTransport(handle)).complete(
            "synthetic-only",
            "gemini-synthetic",
            "instruction",
            {"_image_jpeg": b"synthetic-jpeg", "text": "untrusted source"},
            SearchPlan,
        )
    )
    assert result.value == {"query": "filter"}
    assert result.input_tokens == 10 and result.output_tokens == 7


def test_google_stream_excludes_thoughts_and_validates_final_answer() -> None:
    raw = json.dumps({"text": "Synthetic answer", "source_ids": ["source"]})
    events = [
        {"event_type": "step.start", "index": 0, "step": {"type": "thought"}},
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "thought_summary", "text": "NOT USER OUTPUT"},
        },
        {"event_type": "step.stop", "index": 0},
        {"event_type": "step.start", "index": 1, "step": {"type": "model_output"}},
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "text", "text": raw[:20]},
        },
        {
            "event_type": "step.delta",
            "index": 1,
            "delta": {"type": "text", "text": raw[20:]},
        },
        {"event_type": "step.stop", "index": 1},
        {
            "event_type": "interaction.completed",
            "interaction": {
                "status": "completed",
                "usage": {"total_input_tokens": 10, "total_output_tokens": 5},
            },
        },
    ]

    async def sink(text: str) -> None:
        seen.append(text)

    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx2.Response(
            200,
            content="".join("data: " + json.dumps(event) + "\n\n" for event in events),
        )

    result = asyncio.run(
        GeminiProvider(httpx2.MockTransport(handle)).stream_complete(
            "synthetic", "gemini-synthetic", "instruction", {}, Answer, sink
        )
    )
    assert "".join(seen) == raw
    assert result.value["text"] == "Synthetic answer"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "requires_action", "steps": []},
        {"status": "completed", "steps": [{"type": "function_call", "name": "delete"}]},
        {
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": "NOT JSON"}],
                }
            ],
        },
        {**interaction('{"query":"filter"}'), "usage": {"total_input_tokens": -1}},
    ],
)
def test_google_rejects_invalid_responses_without_exposing_provider_body(
    body: dict[str, Any],
) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=body)

    with pytest.raises(ProviderError) as error:
        asyncio.run(
            GeminiProvider(httpx2.MockTransport(handle)).complete(
                "synthetic-sensitive-key",
                "gemini-synthetic",
                "instruction",
                {},
                SearchPlan,
            )
        )
    assert "synthetic-sensitive-key" not in str(error.value) and "NOT JSON" not in str(
        error.value
    )


def test_google_uses_shared_private_recall_consent_and_preferences() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from fastapi.testclient import TestClient
    from test_chat import FakeProvider

    from lifegather.main import create_app
    from lifegather.memory.schemas import SourceInput
    from lifegather.memory.service import MemoryService

    app = create_app()
    with TestClient(app) as client:
        store = app.state.auth_store
        signed = store.login("gemini", "gemini@example.test", "Gemini", now=2000000000)
        client.cookies.set("lifegather_session", signed.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(
            signed.user, "ai", "google", "Synthetic Gemini", "synthetic"
        )
        fake = FakeProvider()
        app.state.google_provider = fake
        fallback = FakeProvider()
        fallback.fail = True
        app.state.chat_provider = fallback
        MemoryService(store.engine).ingest(
            signed.user, SourceInput(text="Synthetic filter 16x25x1")
        )
        choice = {"credential_id": credential.id, "model": "gemini-synthetic"}
        assert (
            client.put(
                "/api/chat/preferences", headers=headers, json=choice
            ).status_code
            == 204
        )
        assert client.get("/api/chat/preferences").json() == choice
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        url = f"/api/chat/conversations/{conversation}/turns"
        body = {**choice, "request_id": "denied", "mode": "ask", "text": "filter?"}
        assert client.post(url, headers=headers, json=body).json()["state"] == "failed"
        assert not fake.calls
        vault.set_preferences(signed.user, True)
        reply = client.post(
            url, headers=headers, json={**body, "request_id": "allowed"}
        ).json()
        assert reply["state"] == "complete"
        assert reply["result"]["provider"] == "google"
        assert reply["result"]["model"] == "gemini-synthetic"
        assert len(fake.calls) == 2 and not fallback.calls


def test_google_rejects_agents_and_oversized_context_without_network() -> None:
    calls = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(500, text="PRIVATE PROVIDER BODY")

    provider = GeminiProvider(httpx2.MockTransport(handle))
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.complete(
                "synthetic", "antigravity-preview", "instruction", {}, SearchPlan
            )
        )
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.complete(
                "synthetic",
                "gemini-synthetic",
                "instruction",
                {"text": "x" * 40001},
                SearchPlan,
            )
        )
    assert calls == 0
    with pytest.raises(ProviderError) as error:
        asyncio.run(
            provider.complete(
                "synthetic", "gemini-synthetic", "instruction", {}, SearchPlan
            )
        )
    assert calls == 1 and "PRIVATE" not in str(error.value)
