"""Refused Gmail grants and AI keys are remembered and offered for reconnect."""

import asyncio
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session
from test_mailboxes import provider
from test_mcp_http import signed_headers
from test_power_center import NOW
from test_power_center import setup as power_setup

from lifegather.chat.preferences import ChatChoice, ChatPreferences
from lifegather.chat.provider import OpenAIProvider
from lifegather.credentials.keygen import generate
from lifegather.credentials.models import Credential
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mailboxes.service import Mailboxes
from lifegather.main import create_app
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker

# Answers arrive after the key was saved at wall-clock time.
LATER = 4_000_000_000
GRANT = GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic"))


def gmail(token: httpx2.Response, api_status: int = 200) -> httpx2.MockTransport:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "oauth2.googleapis.com":
            return token
        if api_status != 200:
            return httpx2.Response(api_status, json={"error": "PRIVATE detail"})
        if request.url.path.endswith("profile"):
            return httpx2.Response(200, json={"emailAddress": "owner@example.test"})
        return httpx2.Response(200, json={"messages": []})

    return httpx2.MockTransport(respond)


def scan(tmp_path: Path, transport: httpx2.MockTransport) -> dict[str, Any]:
    store, alice, bob, vault, power = power_setup(tmp_path)
    mailbox = Mailboxes(store.engine, vault).connect(alice, GRANT)
    handler = GmailImportHandler(store.engine, vault, provider(transport))
    scans = ScanService(store.engine, ScanRegistry([handler]))
    run = scans.enqueue(
        alice,
        "gmail_import",
        {
            "mailbox_id": mailbox["id"],
            "from_timestamp": 100,
            "until_timestamp": 200,
            "max_messages": 5,
        },
        "first",
    )
    asyncio.run(ScanWorker(scans).run_once())
    return {
        "store": store,
        "alice": alice,
        "bob": bob,
        "vault": vault,
        "power": power,
        "mailbox": mailbox,
        "run": scans.get(alice, run["id"]),
    }


@pytest.mark.parametrize(
    ("token", "api_status"),
    [
        (httpx2.Response(400, json={"error": "invalid_grant"}), 200),
        (httpx2.Response(200, json={"access_token": "synthetic-access"}), 401),
    ],
)
def test_refused_gmail_grant_fails_scan_with_reconnect(
    tmp_path: Path, token: httpx2.Response, api_status: int
) -> None:
    result = scan(tmp_path, gmail(token, api_status))
    store, alice, mailbox = result["store"], result["alice"], result["mailbox"]
    run = result["run"]
    assert run["state"] == "failed"
    assert run["error"].startswith("Gmail access expired or was revoked")
    assert "PRIVATE" not in str(run)
    mailboxes = Mailboxes(store.engine, result["vault"])
    assert mailboxes.list(alice)[0]["needs_reconnect"] is True
    assert mailboxes.list(result["bob"]) == []
    snapshot = result["power"].read(alice)
    source = next(s for s in snapshot.sources if s.id == mailbox["id"])
    assert source.state == "failed" and source.action == "Settings"
    assert source.reconnect is not None
    assert source.reconnect.model_dump() == {
        "kind": "gmail",
        "provider": "gmail",
        "mailbox_id": mailbox["id"],
    }
    issue = next(i for i in snapshot.issues if i.id == mailbox["id"])
    assert issue.reconnect == source.reconnect
    # Consenting again through Google replaces the grant and clears the prompt.
    mailboxes.connect(alice, GRANT)
    assert mailboxes.list(alice)[0]["needs_reconnect"] is False
    again = result["power"].read(alice)
    assert next(s for s in again.sources if s.id == mailbox["id"]).reconnect is None
    store.engine.dispose()


def test_other_gmail_failures_do_not_ask_for_reconnect(tmp_path: Path) -> None:
    result = scan(
        tmp_path, gmail(httpx2.Response(503, json={"error": "invalid_grant"}))
    )
    assert result["run"]["state"] == "failed"
    assert "Reconnect Gmail" not in result["run"]["error"]
    mailboxes = Mailboxes(result["store"].engine, result["vault"])
    assert mailboxes.list(result["alice"])[0]["needs_reconnect"] is False
    result["store"].engine.dispose()


def test_successful_gmail_refresh_records_working(tmp_path: Path) -> None:
    result = scan(
        tmp_path,
        gmail(httpx2.Response(200, json={"access_token": "synthetic-access"})),
    )
    assert result["run"]["state"] == "completed", result["run"]
    with Session(result["store"].engine) as db:
        (row,) = db.query(Credential).all()
        assert row.auth_state == "working" and row.auth_checked_at
    result["store"].engine.dispose()


def test_power_center_reports_refused_and_working_ai_keys(tmp_path: Path) -> None:
    store, alice, _bob, vault, power = power_setup(tmp_path)
    key = vault.save(alice, "ai", "openai", "Synthetic", "do-not-expose")
    vault.set_preferences(alice, True)
    ChatPreferences(store.engine).set(
        alice, ChatChoice(credential_id=key.id, model="synthetic-model")
    )
    vault.record_auth(alice, key.id, "reconnect", read_at=LATER, now=NOW - 5)
    refused = power.read(alice)
    openai = next(s for s in refused.sources if s.id == "openai")
    assert openai.state == "failed" and "Synthetic" in openai.reason
    assert openai.reconnect is not None
    assert openai.reconnect.model_dump() == {
        "kind": "ai",
        "provider": "openai",
        "mailbox_id": None,
    }
    assert next(c for c in refused.capabilities if c.id == "ai_recall").state == (
        "failed"
    )
    assert key.id not in refused.model_dump_json()
    assert [i.id for i in refused.issues if i.reconnect] == ["openai"]
    # A replaced key is unverified again; a later success shows it working.
    replaced = vault.replace(alice, key.id, "new-secret")
    assert replaced.auth_state is None
    assert next(s for s in power.read(alice).sources if s.id == "openai").state == (
        "unknown"
    )
    vault.record_auth(alice, key.id, "working", read_at=LATER, now=NOW - 5)
    working = power.read(alice)
    assert next(s for s in working.sources if s.id == "openai").state == "ready"
    assert next(c for c in working.capabilities if c.id == "ai_recall").state == (
        "ready"
    )
    assert not any(i.id == "ai_setup" for i in working.issues)
    store.engine.dispose()


def test_answer_about_a_replaced_key_is_ignored(tmp_path: Path) -> None:
    store, alice, _bob, vault, _power = power_setup(tmp_path)
    key = vault.save(alice, "ai", "openai", "Synthetic", "old")
    with Session(store.engine) as db, db.begin():
        row = db.get(Credential, key.id)
        assert row is not None
        row.updated_at = LATER + 100
    vault.record_auth(alice, key.id, "reconnect", read_at=LATER)
    assert vault.list(alice)["items"][0]["auth_state"] is None
    store.engine.dispose()


@pytest.mark.parametrize("status", [401, 403])
def test_refused_ai_key_fails_chat_with_reconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    calls: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(status, json={"error": "PRIVATE provider detail"})

    app.state.chat_provider = OpenAIProvider(httpx2.MockTransport(respond))
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
                "label": "Work key",
                "secret": "synthetic-sensitive-token",
            },
        ).json()["id"]
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        turn = client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=alice,
            json={
                "request_id": "ask-1",
                "mode": "ask",
                "text": "Filter size?",
                "credential_id": credential,
                "model": "fixture-model",
            },
        ).json()
        assert len(calls) == 1
        assert turn["state"] == "failed"
        assert turn["result"]["reconnect"] == {
            "kind": "ai",
            "credential_id": credential,
            "provider": "openai",
        }
        assert "Reconnect" in turn["result"]["text"]
        assert "PRIVATE" not in str(turn)
        (entry,) = client.get("/api/credentials", headers=alice).json()["items"]
        assert entry["auth_state"] == "reconnect"
        replaced = client.put(
            f"/api/credentials/{credential}",
            headers=alice,
            json={"secret": "new-synthetic-token"},
        ).json()
        assert replaced["auth_state"] is None
        power = client.get("/api/power", headers=alice)
        assert power.status_code == 200
        assert "synthetic-sensitive-token" not in power.text
