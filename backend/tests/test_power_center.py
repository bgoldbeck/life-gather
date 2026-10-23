import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from database_support import database
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_mcp_http import rpc, signed_headers

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.models import Usage
from lifegather.chat.preferences import ChatChoice, ChatPreferences
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.models import Mailbox
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.service import Mailboxes
from lifegather.main import create_app
from lifegather.power.service import DATA_SECONDS, OBSERVATION_SECONDS, PowerCenter
from lifegather.scans.models import ScanRun, ScanSchedule

pytestmark = pytest.mark.usefixtures("configured_database")

NOW = 1_792_500_000


def setup(
    tmp_path: Path,
) -> tuple[AuthStore, Account, Account, PrivateSettings, PowerCenter]:
    store = AuthStore(database(tmp_path / "power"))
    store.migrate()
    alice = store.login("power-alice", "alice@example.test", "Alice", now=NOW).user
    bob = store.login("power-bob", "bob@example.test", "Bob", now=NOW).user
    vault = PrivateSettings(store.engine, b"k" * 32)
    service = PowerCenter(
        store.engine,
        vault_enabled=True,
        gmail_enabled=True,
        handlers={"gmail_import", "gmail_discovery"},
        clock=lambda: NOW,
    )
    return store, alice, bob, vault, service


def connect(
    store: AuthStore, actor: Account, vault: PrivateSettings, name: str
) -> dict[str, Any]:
    return Mailboxes(store.engine, vault, clock=lambda: NOW - 100).connect(
        actor,
        GmailGrant(
            address=name + "@example.test", refresh_token=SecretStr("never-expose")
        ),
    )


def run(
    store: AuthStore, actor: Account, mailbox: dict[str, Any], **changes: Any
) -> str:
    identifier = str(uuid4())
    values = dict(
        id=identifier,
        user_id=actor.id,
        handler_key="gmail_import",
        resource_key="gmail:" + mailbox["id"],
        config_json=json.dumps({"mailbox_revision": mailbox["revision"]}),
        cursor_json="{}",
        request_id=identifier,
        fingerprint=identifier,
        state="completed",
        cancel_requested=False,
        scanned=3,
        imported=2,
        existing=1,
        skipped=0,
        steps=1,
        attempts=1,
        truncated=False,
        error=None,
        lease_token=None,
        lease_until=None,
        created_at=NOW - 50,
        updated_at=NOW - 10,
        started_at=NOW - 49,
        completed_at=NOW - 10,
    )
    with Session(store.engine) as db, db.begin():
        db.add(ScanRun(**{**values, **changes}))
    return identifier


def test_local_readiness_ai_consent_defaults_budget_and_redundancy(
    tmp_path: Path,
) -> None:
    store, alice, bob, vault, service = setup(tmp_path)
    empty = service.read(alice)
    assert empty.score == 55 and empty.minimum_score == empty.maximum_score == 55
    assert sum(c.weight for c in empty.capabilities) == 100
    assert empty.connected_sources == empty.completed_scans_7d == 0
    connection = vault.save(alice, "ai", "openai", "Synthetic", "do-not-expose")
    vault.set_preferences(alice, True)
    ChatPreferences(store.engine).set(
        alice, ChatChoice(credential_id=connection.id, model="synthetic-model")
    )
    configured = service.read(alice)
    assert configured.score is None
    assert (configured.minimum_score, configured.maximum_score) == (55, 80)
    assert next(
        c for c in configured.capabilities if c.id == "ai_recall"
    ).available_to_request
    vault.save(alice, "ai", "openai", "Redundant", "second-secret")
    redundant = service.read(alice)
    assert redundant.capabilities == configured.capabilities
    assert redundant.connected_sources == configured.connected_sources
    assert redundant.minimum_score == configured.minimum_score
    assert redundant.maximum_score == configured.maximum_score
    assert service.read(bob).score == 55
    text = configured.model_dump_json()
    assert all(
        secret not in text
        for secret in (connection.id, "do-not-expose", "ciphertext", "nonce", bob.id)
    )
    day = datetime.fromtimestamp(NOW, UTC).date().isoformat()
    with Session(store.engine) as db, db.begin():
        db.add(
            Usage(
                user_id=alice.id, day=day, requests=20, input_tokens=0, output_tokens=0
            )
        )
    limited = service.read(alice)
    assert limited.score == 55
    assert any("limit reached" in i.reason for i in limited.issues)
    assert limited.ai_resets_at > NOW
    vault.set_preferences(alice, False)
    assert (
        next(c for c in service.read(alice).capabilities if c.id == "ai_recall").state
        == "disabled"
    )


def test_grant_revision_freshness_failures_and_healthy_alternatives(
    tmp_path: Path,
) -> None:
    store, alice, bob, vault, service = setup(tmp_path)
    mailbox = connect(store, alice, vault, "private-alice")
    assert (
        next(
            c for c in service.read(alice).capabilities if c.id == "gmail_import"
        ).state
        == "unknown"
    )
    identifier = run(store, alice, mailbox)
    snapshot = service.read(alice)
    assert snapshot.completed_scans_7d == 1 and snapshot.imported_messages_7d == 2
    assert (
        next(s for s in snapshot.sources if s.id == mailbox["id"]).last_run_id
        == identifier
    )
    assert (
        next(c for c in snapshot.capabilities if c.id == "gmail_import").state
        == "ready"
    )
    assert "private-alice" not in service.read(bob).model_dump_json()
    with Session(store.engine) as db, db.begin():
        row = db.get(ScanRun, identifier)
        assert row is not None
        row.completed_at = NOW - OBSERVATION_SECONDS - 1
    source = next(s for s in service.read(alice).sources if s.id == mailbox["id"])
    assert source.state == "stale" and source.freshness == "current"
    with Session(store.engine) as db, db.begin():
        row = db.get(ScanRun, identifier)
        assert row is not None
        row.completed_at = NOW - DATA_SECONDS - 1
    source = next(s for s in service.read(alice).sources if s.id == mailbox["id"])
    assert source.freshness == "stale"
    failed = run(
        store,
        alice,
        mailbox,
        state="failed",
        completed_at=None,
        created_at=NOW - 5,
        updated_at=NOW - 4,
        error="revoked-token with private provider payload",
    )
    snapshot = service.read(alice)
    assert next(s for s in snapshot.sources if s.id == mailbox["id"]).state == "failed"
    assert failed in [i.run_id for i in snapshot.issues]
    assert "revoked-token" not in snapshot.model_dump_json()
    run(
        store,
        alice,
        mailbox,
        state="canceled",
        created_at=NOW - 2,
        updated_at=NOW - 1,
        completed_at=None,
    )
    assert (
        next(s for s in service.read(alice).sources if s.id == mailbox["id"]).state
        == "failed"
    )
    other = connect(store, alice, vault, "alternative")
    run(store, alice, other)
    assert (
        next(
            c for c in service.read(alice).capabilities if c.id == "gmail_import"
        ).state
        == "ready"
    )
    with Session(store.engine) as db, db.begin():
        original = db.get(Mailbox, mailbox["id"])
        assert original is not None
        original.revision += 1
    assert (
        next(s for s in service.read(alice).sources if s.id == mailbox["id"]).state
        == "unknown"
    )


def test_expired_lease_paused_overdue_schedules_and_bounded_diagnostics(
    tmp_path: Path,
) -> None:
    store, alice, bob, vault, service = setup(tmp_path)
    mailbox = connect(store, alice, vault, "lease")
    expired = run(
        store, alice, mailbox, state="running", lease_until=NOW - 1, completed_at=None
    )
    with Session(store.engine) as db, db.begin():
        for enabled in (False, True):
            identifier = str(uuid4())
            db.add(
                ScanSchedule(
                    id=identifier,
                    user_id=alice.id,
                    request_id=identifier,
                    fingerprint=identifier,
                    label="Synthetic",
                    handler_key="gmail_import",
                    config_json="{}",
                    timezone="UTC",
                    cadence="daily",
                    weekday=0,
                    local_time="09:00",
                    lookback_days=1,
                    enabled=enabled,
                    revision=1,
                    next_run=NOW - 1000,
                    last_due=None,
                    last_run_id=None,
                    last_status="scheduled" if enabled else "paused",
                    created_at=NOW - 100,
                    updated_at=NOW - 100,
                )
            )
    snapshot = service.read(alice)
    assert snapshot.paused_schedules == 1
    assert any(
        i.run_id == expired and i.title == "Expired scan lease" for i in snapshot.issues
    )
    assert sum(i.title == "Schedule needs attention" for i in snapshot.issues) == 1
    assert service.read(bob).issues != snapshot.issues
    for _ in range(12):
        run(store, alice, mailbox, state="failed", completed_at=None)
    bounded = service.read(alice)
    assert bounded.issues_truncated
    assert len([i for i in bounded.issues if i.run_id]) == 10
    assert len(bounded.model_dump_json().encode()) < 32768


def test_http_mcp_owner_authorization_and_read_only_diagnostics() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "power-alice")
        bob, _ = signed_headers(app, "power-bob")
        assert client.get("/api/power").status_code == 401
        response = client.get("/api/power", headers=alice)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        engine = app.state.auth_store.engine
        with Session(engine) as db:
            before = db.scalar(select(func.count()).select_from(ScanRun))
        result = rpc(client, alice, "power_center_get", {}).json()
        assert "result" in result, result
        assert not result["result"].get("isError"), result
        assert "minimum_score" in str(result)
        assert (
            rpc(client, bob, "power_center_get", {"user_id": actor.id}).status_code
            == 400
        )
        assert (
            rpc(
                client, {**alice, "X-CSRF-Token": "wrong"}, "power_center_get", {}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/chat/context",
                headers=alice,
                json={"page": "Power Center", "entity_id": None},
            ).status_code
            == 200
        )
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ScanRun)) == before
        app.state.auth_store.logout(alice["Cookie"].split("=", 1)[1])
        assert client.get("/api/power", headers=alice).status_code == 401
