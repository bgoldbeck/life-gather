import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_mcp_http import rpc, signed_headers

from lifegather.auth.store import AuthStore
from lifegather.chat.models import Turn
from lifegather.chat.provider import (
    Completion,
    OpenAIProvider,
    ProviderError,
    SearchPlan,
)
from lifegather.chat.service import ChatService, TurnInput
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.service import MemoryError


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.bad_citation = False
        self.fail = False

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion:
        self.calls.append(payload)
        if self.fail:
            raise ValueError("PRIVATE PROVIDER BODY and synthetic-sensitive-token")
        if schema is SearchPlan:
            return Completion({"query": "filter"}, 10, 5)
        return Completion(
            {
                "text": "Your original note says 16x25x1.",
                "source_ids": ["foreign"]
                if self.bad_citation
                else [payload["evidence"][0]["id"]],
            },
            20,
            10,
        )


def send(
    client: TestClient,
    headers: dict[str, str],
    conversation: str,
    key: str,
    mode: str,
    text: str,
    **extra: str,
) -> Any:
    return client.post(
        f"/api/chat/conversations/{conversation}/turns",
        headers=headers,
        json={"request_id": key, "mode": mode, "text": text, **extra},
    )


def test_text_capture_recall_replay_restart_and_owner_scope() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/chat/conversations").status_code == 401
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        assert (
            client.post(
                "/api/chat/conversations", headers={"Cookie": alice["Cookie"]}
            ).status_code
            == 403
        )
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        original = "My downstairs filter is 16x25x1. <script>alert(1)</script>"
        saved = send(client, alice, conversation, "note-1", "save", original)
        assert saved.status_code == 200, saved.text
        turn = saved.json()
        assert turn["state"] == "complete", turn
        source = turn["result"]["sources"][0]["id"]
        assert (
            send(client, alice, conversation, "note-1", "save", original).json() == turn
        )
        assert (
            send(client, alice, conversation, "note-1", "save", "changed").status_code
            == 400
        )
        assert (
            send(client, bob, conversation, "steal", "search", "filter").status_code
            == 400
        )
        assert client.get(f"/api/chat/sources/{source}", headers=bob).status_code == 400
        assert client.get("/api/chat/conversations", headers=bob).json()["items"] == []
        second = client.post("/api/chat/conversations", headers=alice).json()["id"]
        recalled = send(client, alice, second, "search-1", "search", "filter").json()
        assert recalled["result"]["sources"][0]["id"] == source
        assert (
            client.get(f"/api/chat/sources/{source}", headers=alice).json()["text"]
            == original
        )
        # Source capture shares the exact same idempotency contract via MCP.
        replay = rpc(
            client,
            alice,
            "memory_save_text",
            {"request_id": "note-1", "text": original},
        )
        assert replay.json()["result"]["structuredContent"]["source"]["id"] == source
        assert (
            client.get("/api/chat/conversations", headers=alice).headers[
                "cache-control"
            ]
            == "no-store"
        )
        assert (
            send(client, alice, conversation, "huge", "save", "x" * 4001).status_code
            == 422
        )
        too_big = client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=alice,
            content=b"x" * 33000,
        )
        assert too_big.status_code == 413
    # A fresh application/process context uses the existing database and session.
    with TestClient(create_app()) as restarted:
        history = restarted.get(
            f"/api/chat/conversations/{conversation}/turns", headers=alice
        ).json()
        assert history["items"][0] == turn
        assert (
            restarted.get(f"/api/chat/sources/{source}", headers=alice).json()["text"]
            == original
        )


def test_openai_consent_budget_citations_failure_and_no_duplicate_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    fake = FakeProvider()
    app.state.chat_provider = fake
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "alice")
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Test",
                "secret": "synthetic-sensitive-token",
            },
        ).json()["id"]
        params = {"credential_id": credential, "model": "fixture-model"}
        send(client, alice, conversation, "note", "save", "My filter is 16x25x1.")
        denied = send(
            client, alice, conversation, "no-consent", "ask", "Filter size?", **params
        )
        assert denied.json()["state"] == "failed" and not fake.calls
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        response = send(
            client, alice, conversation, "ask-1", "ask", "Filter size?", **params
        )
        assert response.json()["state"] == "complete", response.text
        assert len(fake.calls) == 2
        assert (
            send(
                client, alice, conversation, "ask-1", "ask", "Filter size?", **params
            ).json()
            == response.json()
        )
        assert len(fake.calls) == 2
        meter = client.get("/api/chat/usage", headers=alice).json()
        assert meter["requests"] == 1 and meter["input_tokens"] == 30
        fake.bad_citation = True
        bad = send(
            client, alice, conversation, "bad-cite", "ask", "Filter size?", **params
        )
        assert bad.json()["state"] == "failed"
        assert "foreign" not in bad.text
        fake.fail = True
        failed = send(client, alice, conversation, "failed", "ask", "Filter?", **params)
        assert failed.json()["state"] == "failed"
        assert (
            "PRIVATE" not in failed.text
            and "synthetic-sensitive-token" not in failed.text
        )
        # Failed requests retain their reservation and cannot silently retry charges.
        for index in range(17):
            send(
                client,
                alice,
                conversation,
                f"limit-{index}",
                "ask",
                "Filter?",
                **params,
            )
        before = len(fake.calls)
        limit = send(
            client, alice, conversation, "over-limit", "ask", "Filter?", **params
        )
        assert limit.json()["state"] == "failed" and len(fake.calls) == before
        assert client.get("/api/chat/usage", headers=alice).json()["requests"] == 20


def test_provider_contract_bounds_and_redaction() -> None:
    requests: list[dict[str, Any]] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        requests.append(body)
        return httpx2.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"query":"filter"}'},
                        ],
                    }
                ],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            },
        )

    provider = OpenAIProvider(httpx2.MockTransport(respond))
    result = asyncio.run(
        provider.complete(
            "synthetic-secret", "fixture", "search", {"question": "filter"}, SearchPlan
        )
    )
    assert result.value == {"query": "filter"}
    assert requests[0]["store"] is False and requests[0]["max_output_tokens"] == 1500
    assert "tools" not in requests[0] and "previous_response_id" not in requests[0]
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.complete(
                "secret", "fixture", "search", {"text": "x" * 40001}, SearchPlan
            )
        )
    assert len(requests) == 1
    failing = OpenAIProvider(
        httpx2.MockTransport(lambda _: httpx2.Response(400, text="PRIVATE secret"))
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(failing.complete("secret", "fixture", "search", {}, SearchPlan))
    assert "PRIVATE" not in str(error.value) and "secret" not in str(error.value)


def test_cancel_stops_inflight_provider_without_another_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = tmp_path / "cancel-vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    started = threading.Event()
    stopped = threading.Event()

    class SlowProvider(FakeProvider):
        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: type[BaseModel],
        ) -> Completion:
            self.calls.append(payload)
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                stopped.set()
                raise
            raise AssertionError("Canceled request should not complete")

    app = create_app()
    fake = SlowProvider()
    app.state.chat_provider = fake
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Test",
                "secret": "fake",
            },
        ).json()["id"]
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                send,
                client,
                alice,
                conversation,
                "cancel-me",
                "ask",
                "Filter?",
                credential_id=credential,
                model="fixture",
            )
            assert started.wait(5)
            assert (
                client.post(
                    "/api/chat/requests/cancel-me/cancel", headers=bob
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/chat/requests/cancel-me/cancel", headers=alice
                ).json()["state"]
                == "canceled"
            )
            assert future.result(timeout=5).json()["state"] == "canceled"
        assert stopped.is_set() and len(fake.calls) == 1
        assert client.get("/api/chat/usage", headers=alice).json()["requests"] == 1


def test_concurrent_request_ids_pagination_and_snapshot_restore(tmp_path: Path) -> None:
    auth = AuthStore(tmp_path / "chat.sqlite3")
    auth.migrate()
    actor = auth.login("alice", "a@example.test", "Alice", now=1).user
    chat = ChatService(auth.engine)
    conversation = chat.create(actor)["id"]
    data = TurnInput(request_id="same", mode="save", text="my filter")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: chat.begin(actor, conversation, data), range(6))
        )
    assert sum(fresh for _, fresh in results) == 1
    turn_id = results[0][0]["id"]
    chat.finish(actor, turn_id, {"text": "Saved"})
    for index in range(27):
        row, _ = chat.begin(
            actor,
            conversation,
            TurnInput(request_id=f"r{index}", mode="save", text=f"note {index}"),
        )
        chat.finish(actor, row["id"], {"text": "Saved"})
    first = chat.turns(actor, conversation)
    second = chat.turns(actor, conversation, first["next_cursor"])
    assert len(first["items"]) == 25 and len(second["items"]) == 3
    assert chat.recent(actor, conversation)[-1]["text"] == "note 26"
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(Turn)))) == 28
    backup = tmp_path / "restored.sqlite3"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(backup)
    restored.migrate()
    assert ChatService(restored.engine).turns(actor, conversation) == first
    with pytest.raises(MemoryError):
        chat.turns(actor, conversation, "unknown-cursor")
