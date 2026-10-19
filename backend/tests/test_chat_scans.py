import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from test_mailboxes import provider
from test_mcp_http import signed_headers
from test_reconciliation import setup

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.service import ChatService, TurnInput
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mailboxes.service import Mailboxes
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.service import ScanService


def test_http_chat_scan_replay_authorization_and_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lifegather.credentials.keygen import generate
    from lifegather.scans.worker import ScanWorker

    async def idle_worker(self: ScanWorker) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(ScanWorker, "serve", idle_worker)
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        if request.url.host == "oauth2.googleapis.com":
            return httpx2.Response(200, json={"access_token": "synthetic"})
        if request.url.path.endswith("profile"):
            return httpx2.Response(200, json={"emailAddress": "owner@example.test"})
        assert request.url.path.endswith("messages")
        return httpx2.Response(200, json={"messages": []})

    app.state.gmail_provider = provider(httpx2.MockTransport(respond))
    with TestClient(app) as client:
        headers, owner = signed_headers(app, "scan-owner")
        foreign, _ = signed_headers(app, "scan-foreign")
        scans = app.state.scan_service
        mailbox = Mailboxes(
            app.state.auth_store.engine, app.state.private_settings
        ).connect(
            owner,
            GmailGrant(
                address="owner@example.test", refresh_token=SecretStr("synthetic")
            ),
        )
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        path = f"/api/chat/conversations/{conversation}/turns"
        body = request(
            {
                "mailbox_id": mailbox["id"],
                "from_timestamp": 100,
                "until_timestamp": 200,
                "max_messages": 5,
            }
        ).model_dump()
        assert client.post(path, json=body).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": headers["Cookie"]}, json=body
            ).status_code
            == 403
        )
        assert client.post(path, headers=foreign, json=body).status_code == 400
        invalid = {**body, "scan": {**body["scan"], "max_messages": 51}}
        assert client.post(path, headers=headers, json=invalid).status_code == 422
        assert scans.list(owner)["items"] == []
        # A process interruption after saving the pending request but before the
        # atomic enqueue can be recovered by the same explicit HTTP retry.
        ChatService(app.state.auth_store.engine).begin(
            owner, conversation, TurnInput.model_validate(body)
        )
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["state"] == "complete"
        run_id = saved["result"]["scan_run_id"]
        assert client.post(path, headers=headers, json=body).json() == saved
        assert len(scans.list(owner)["items"]) == 1
        assert client.get(f"/api/scans/{run_id}", headers=foreign).status_code == 400
        assert client.get("/api/chat/usage", headers=headers).json()["requests"] == 0
        # Exercise the actual worker against a synthetic transport only.
        asyncio.run(ScanWorker(scans).run_once())
        assert scans.get(owner, run_id)["state"] == "completed"
        assert seen and all("googleapis.com" in url for url in seen)
        # Cancelling a finished Chat request cannot silently cancel an independent job.
        client.post("/api/chat/requests/scan/cancel", headers=headers)
        assert scans.get(owner, run_id)["state"] == "completed"


def prepared(
    tmp_path: Path,
) -> tuple[
    AuthStore,
    Account,
    Account,
    ChatService,
    ScanService,
    Mailboxes,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    MemoryService,
]:
    auth, actor, foreign, memory, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"g" * 32)
    mailboxes = Mailboxes(auth.engine, vault)
    mailbox = mailboxes.connect(
        actor,
        GmailGrant(
            address="owner@example.test", refresh_token=SecretStr("synthetic-only")
        ),
    )
    other = mailboxes.connect(
        foreign,
        GmailGrant(
            address="foreign@example.test", refresh_token=SecretStr("synthetic-only")
        ),
    )

    def no_network(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("Enqueue must not contact Gmail or AI")

    scans = ScanService(
        auth.engine,
        ScanRegistry(
            [
                GmailImportHandler(
                    auth.engine, vault, provider(httpx2.MockTransport(no_network))
                )
            ]
        ),
    )
    chat = ChatService(auth.engine)
    scope = {
        "mailbox_id": mailbox["id"],
        "from_timestamp": 100,
        "until_timestamp": 200,
        "max_messages": 5,
        "query": "receipt",
    }
    return auth, actor, foreign, chat, scans, mailboxes, mailbox, other, scope, memory


def request(scope: dict[str, Any], request_id: str = "scan") -> TurnInput:
    return TurnInput.model_validate(
        {
            "request_id": request_id,
            "mode": "scan_email",
            "text": "Scan connected email for original text evidence.",
            "scan": scope,
        }
    )


def test_chat_scan_atomically_saves_job_result_replay_and_snapshot(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, chat, scans, _, _, _, scope, memory = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = request(scope)
    row, fresh = chat.begin(actor, conversation, data)
    assert fresh and row["state"] == "pending"
    result = chat.start_scan(actor, conversation, data, scans)
    assert result["state"] == "complete"
    identifier = result["result"]["scan_run_id"]
    run = scans.get(actor, identifier)
    assert run["handler_key"] == "gmail_import" and run["state"] == "queued"
    assert (
        run["scope"]["mailbox_id"] == scope["mailbox_id"]
        and run["scope"]["max_messages"] == 5
    )
    assert scans.list(foreign)["items"] == []
    replay, fresh = chat.begin(actor, conversation, data)
    assert not fresh and replay == result
    assert chat.start_scan(actor, conversation, data, scans) == result
    assert len(scans.list(actor)["items"]) == 1
    assert memory.export_page(actor, "sources")["items"] == []
    assert memory.export_page(actor, "entities")["items"] == []
    assert chat.usage(actor)["requests"] == 0
    snapshot = tmp_path / "restore.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    again, fresh = ChatService(restored.engine).begin(actor, conversation, data)
    assert not fresh and again == result
    assert (
        ScanService(restored.engine, scans.registry).get(actor, identifier)["state"]
        == "queued"
    )
    restored.engine.dispose()


def test_chat_scan_rolls_back_queue_when_result_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, actor, _, chat, scans, _, _, _, scope, _ = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = request(scope)
    chat.begin(actor, conversation, data)
    original = chat.view

    def fail(row: Any) -> dict[str, Any]:
        raise RuntimeError("Synthetic result serialization failure")

    monkeypatch.setattr(chat, "view", fail)
    with pytest.raises(RuntimeError):
        chat.start_scan(actor, conversation, data, scans)
    monkeypatch.setattr(chat, "view", original)
    assert scans.list(actor)["items"] == []
    assert chat.turns(actor, conversation)["items"][0]["state"] == "pending"


def test_canceled_chat_scan_does_not_enqueue_and_changed_arguments_conflict(
    tmp_path: Path,
) -> None:
    _, actor, _, chat, scans, _, _, _, scope, _ = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = request(scope)
    chat.begin(actor, conversation, data)
    canceled = chat.cancel(actor, data.request_id)
    assert chat.start_scan(actor, conversation, data, scans) == canceled
    assert scans.list(actor)["items"] == []
    with pytest.raises(MemoryError):
        chat.start_scan(
            actor, conversation, request({**scope, "query": "different"}), scans
        )


def test_chat_scan_refuses_foreign_or_disconnected_mailbox(tmp_path: Path) -> None:
    _, actor, _, chat, scans, mailboxes, mailbox, other, scope, _ = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = request({**scope, "mailbox_id": other["id"]})
    chat.begin(actor, conversation, data)
    with pytest.raises(MemoryError):
        chat.start_scan(actor, conversation, data, scans)
    assert scans.list(actor)["items"] == []
    chat.cancel(actor, data.request_id)
    mailboxes.disconnect(actor, mailbox["id"], mailbox["revision"])
    data = request(scope, "disconnected")
    chat.begin(actor, conversation, data)
    with pytest.raises(MemoryError):
        chat.start_scan(actor, conversation, data, scans)
    assert scans.list(actor)["items"] == []


def test_concurrent_chat_scan_retries_queue_one_job(tmp_path: Path) -> None:
    _, actor, _, chat, scans, _, _, _, scope, _ = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = request(scope)
    chat.begin(actor, conversation, data)

    def start(_: int) -> dict[str, Any]:
        return chat.start_scan(actor, conversation, data, scans)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(start, range(2)))
    assert first == second and len(scans.list(actor)["items"]) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"max_messages": 51},
        {"until_timestamp": 100},
        {"until_timestamp": 32 * 86400 + 100},
        {"handler_key": "gmail_discovery"},
        {"credential_id": "ai"},
    ],
)
def test_chat_scan_rejects_invalid_or_broader_scope(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        request(
            {
                "mailbox_id": "mailbox",
                "from_timestamp": 100,
                "until_timestamp": 200,
                **changes,
            }
        )


def test_existing_chat_fingerprints_do_not_gain_empty_scan_field(
    tmp_path: Path,
) -> None:
    _, actor, _, chat, scans, _, _, _, _, _ = prepared(tmp_path)
    conversation = chat.create(actor)["id"]
    data = TurnInput(request_id="legacy", mode="save", text="Synthetic original text.")
    row, _ = chat.begin(actor, conversation, data)
    from sqlalchemy.orm import Session

    from lifegather.chat.models import Turn

    with Session(chat.engine) as db:
        stored = db.get(Turn, row["id"])
        assert stored is not None
        assert stored.fingerprint == fingerprint(
            [
                conversation,
                data.model_dump(exclude={"source_id", "photo_id", "scan", "context"}),
            ]
        )
    result = chat.finish(actor, row["id"], {"text": "Saved original."})
    replay, fresh = chat.begin(actor, conversation, data)
    assert not fresh and replay == result and scans.list(actor)["items"] == []
