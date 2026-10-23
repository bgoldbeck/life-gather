"""Erasing a Gmail connection or a scan removes what came from it, nothing else."""

import asyncio
from pathlib import Path
from typing import Any

import httpx2
import pytest
from database_support import database
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from stored_files import files
from test_email_discovery import harness
from test_gmail_attachments import PHOTO, RECEIPT, encoded, message
from test_mailboxes import provider
from test_mcp_http import signed_headers
from test_reconciliation import setup

from lifegather.auth.store import Account, AuthStore
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.models import Document
from lifegather.documents.service import DocumentService
from lifegather.erasure.service import (
    SOURCE_ERASED,
    ErasureConfirm,
    ErasureError,
    ErasureTarget,
    SourceErasure,
)
from lifegather.mailboxes.attachments import GmailAttachmentHandler
from lifegather.mailboxes.models import Mailbox
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.service import Mailboxes
from lifegather.main import create_app
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.models import Assertion, Audit, Entity, Episode
from lifegather.memory.notes import NoteConflict
from lifegather.memory.restore import PersonalRestore
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryService
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoService
from lifegather.scans.models import ScanRun, ScanRunItem
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker


def rows(engine: Engine, user_id: str) -> dict[str, int]:
    """Row count of every owned table for one account."""
    with engine.connect() as connection:
        tables = connection.scalars(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND column_name = 'user_id' "
                "ORDER BY 1"
            )
        ).all()
        return {
            table: int(
                connection.scalar(
                    text(f'SELECT count(*) FROM "{table}" WHERE user_id = :u'),
                    {"u": user_id},
                )
                or 0
            )
            for table in tables
        }


def erase(
    service: SourceErasure, actor: Account, kind: str, identifier: str
) -> dict[str, Any]:
    target = ErasureTarget(kind=kind, id=identifier)  # type: ignore[arg-type]
    preview = service.preview(actor, target)
    result = service.erase(
        actor,
        ErasureConfirm(
            kind=target.kind, id=identifier, fingerprint=preview["fingerprint"]
        ),
    )
    assert result["counts"] == preview["counts"]
    return result


def email_sources(engine: Engine, actor: Account) -> list[str]:
    with Session(engine) as db:
        return list(
            db.scalars(
                select(Episode.id)
                .where(Episode.user_id == actor.id, Episode.source_type == "email")
                .order_by(Episode.recorded_at)
            )
        )


def scanned(tmp_path: Path) -> Any:
    auth, actor, bob, memory, reconcile, vault, ai, scans, config = harness(tmp_path)
    run = scans.enqueue(actor, "gmail_discovery", config, "first")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "completed"
    return auth, actor, bob, memory, reconcile, vault, scans, config, run


def test_erasing_a_mailbox_removes_everything_from_it_and_nothing_else(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile, vault, scans, config, run = scanned(tmp_path)
    engine = auth.engine
    note = memory.ingest(
        actor, SourceInput(text="My own synthetic note", external_id="n")
    )
    memory.ingest(bob, SourceInput(text="Bob's synthetic note", external_id="b"))
    assert len(reconcile.inventory(actor)) == 1
    bob_before = rows(engine, bob.id)
    service = SourceErasure(engine, files(engine))
    target = ErasureTarget(kind="mailbox", id=config["mailbox_id"])
    preview = service.preview(actor, target)
    counts = preview["counts"]
    assert counts["memories"] == 2 and counts["assets"] == 1
    assert counts["connections"] == 1 and counts["scans"] == 1
    assert counts["kept_assets"] == 0
    result = service.erase(
        actor, ErasureConfirm(**target.model_dump(), fingerprint=preview["fingerprint"])
    )
    assert result["erased"] is True and result["rows"] > 10
    after = rows(engine, actor.id)
    for table in (
        "mailboxes",
        "scan_runs",
        "scan_run_items",
        "email_discoveries",
        "memory_entities",
        "memory_facts",
        "memory_evidence",
        "reconciliation_observations",
        "reconciliation_purchases",
        "reconciliation_bindings",
    ):
        assert after[table] == 0, table
    assert reconcile.inventory(actor) == []
    assert email_sources(engine, actor) == []
    assert memory.get_source(actor, note.id).text == "My own synthetic note"
    with Session(engine) as db:
        kinds = set(
            db.scalars(select(Credential.kind).where(Credential.user_id == actor.id))
        )
        assert kinds == {"ai"}  # The mailbox's Gmail grant is gone, AI kept.
        audits = list(
            db.scalars(select(Audit.operation).where(Audit.user_id == actor.id))
        )
        assert audits.count(SOURCE_ERASED) == 1
        assert "email_discovery" not in audits and "mailbox_connected" not in audits
        index = db.scalar(
            text(
                "SELECT count(*) FROM memory_fts "
                "WHERE user_id = :u AND kind <> 'source'"
            ),
            {"u": actor.id},
        )
        assert index == 0
    assert rows(engine, bob.id) == bob_before
    with pytest.raises(ErasureError) as missing:
        service.preview(actor, target)
    assert missing.value.status == 404
    # The account's archive still exports and restores cleanly.
    archive = PersonalArchive(engine, files(engine)).download(actor)
    other = AuthStore(database(tmp_path / "other"))
    other.migrate()
    fresh = other.login("r", "r@example.test", "R", now=1).user
    PersonalRestore(other.engine, files(other.engine)).restore(fresh, archive)
    assert MemoryService(other.engine).get_source(fresh, note.id).text == note.text
    other.engine.dispose()
    engine.dispose()


def test_records_a_kept_source_supports_survive_attributed_to_it(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, _, _, config, _ = scanned(tmp_path)
    engine = auth.engine
    (asset,) = reconcile.inventory(actor)
    note = memory.ingest(
        actor, SourceInput(text="My trimmer has serial TR-1", external_id="serial")
    )
    serial = memory.assert_fact(
        actor,
        FactInput(
            subject_id=asset,
            predicate="serial_number",
            value="TR-1",
            source_id=note.id,
            quote="serial TR-1",
            operation_key="manual:serial",
        ),
    )
    with Session(engine) as db:
        owned = db.scalar(
            select(Assertion.id).where(
                Assertion.subject_id == asset, Assertion.predicate == "owned"
            )
        )
    assert owned
    memory.attach_evidence(actor, owned, note.id, "My trimmer")
    service = SourceErasure(engine, files(engine))
    result = erase(service, actor, "mailbox", config["mailbox_id"])
    assert result["counts"]["kept_assets"] == 1 and result["counts"]["assets"] == 0
    with Session(engine) as db:
        entity = db.get(Entity, asset)
        assert entity is not None and entity.source_id == note.id
        kept = set(
            db.scalars(select(Assertion.id).where(Assertion.subject_id == asset))
        )
    assert {serial.id, owned} <= kept
    evidence = memory.facts(actor, asset)
    assert all(e["source_id"] == note.id for fact in evidence for e in fact.evidence), (
        evidence
    )
    engine.dispose()


def test_erased_corrections_restore_the_kept_value_and_kept_corrections_stay(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _, _, _, config, _ = scanned(tmp_path)
    engine = auth.engine
    email = email_sources(engine, actor)[0]
    note = memory.ingest(actor, SourceInput(text="My synthetic mower", external_id="m"))
    mower = memory.create_entity(
        actor,
        EntityInput(name="Mower", kind="asset", source_id=note.id, operation_key="m"),
    )

    def fact(value: str, source: str, key: str) -> FactInput:
        return FactInput(
            subject_id=mower.id,
            predicate="color" if key.startswith("c") else "model_name",
            value=value,
            source_id=source,
            operation_key=key,
        )

    mine = memory.assert_fact(actor, fact("green", note.id, "c1"))
    from_email = memory.correct_fact(actor, mine.id, fact("red", email, "c2"))
    emailed = memory.assert_fact(actor, fact("M1", email, "m1"))
    corrected = memory.correct_fact(actor, emailed.id, fact("M2", note.id, "m2"))
    erase(SourceErasure(engine, files(engine)), actor, "mailbox", config["mailbox_id"])
    with Session(engine) as db:
        restored = db.get(Assertion, mine.id)
        assert restored is not None and restored.superseded_at is None
        assert db.get(Assertion, from_email.id) is None
        assert db.get(Assertion, emailed.id) is None
        kept = db.get(Assertion, corrected.id)
        assert (
            kept is not None and kept.replaces_id is None and kept.superseded_at is None
        )
    engine.dispose()


def test_changed_source_and_running_scan_refuse(tmp_path: Path) -> None:
    auth, actor, bob, memory, reconcile, _, scans, config, _ = scanned(tmp_path)
    engine = auth.engine
    service = SourceErasure(engine, files(engine))
    target = ErasureTarget(kind="mailbox", id=config["mailbox_id"])
    preview = service.preview(actor, target)
    (asset,) = reconcile.inventory(actor)
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=asset,
            predicate="color",
            value="orange",
            source_id=email_sources(engine, actor)[0],
            operation_key="late",
        ),
    )
    with pytest.raises(NoteConflict):
        service.erase(
            actor,
            ErasureConfirm(**target.model_dump(), fingerprint=preview["fingerprint"]),
        )
    assert len(reconcile.inventory(actor)) == 1
    # Another account cannot see, preview or erase it.
    with pytest.raises(ErasureError):
        service.preview(bob, target)
    scans.enqueue(actor, "gmail_discovery", config, "pending")
    with pytest.raises(ErasureError) as running:
        service.preview(actor, target)
    assert running.value.status == 409
    engine.dispose()


def test_erasing_one_scan_keeps_the_connection_and_its_schedule(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, reconcile, _, scans, config, run = scanned(tmp_path)
    engine = auth.engine
    scheduler = ScheduleService(scans)
    scheduler.create(
        actor,
        ScheduleInput(
            label="Synthetic discovery",
            handler_key="gmail_discovery",
            config={
                k: v
                for k, v in config.items()
                if k not in {"from_timestamp", "until_timestamp"}
            },
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=7,
            request_id="schedule",
        ),
    )
    with Session(engine) as db:
        db.execute(text("UPDATE scan_schedules SET last_run_id = :r"), {"r": run["id"]})
        db.commit()
    result = erase(SourceErasure(engine, files(engine)), actor, "scan", run["id"])
    assert result["counts"]["scans"] == 1 and result["counts"]["connections"] == 0
    assert result["counts"]["schedules"] == 0
    assert reconcile.inventory(actor) == []
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Mailbox)) == 1
        assert db.scalar(select(func.count()).select_from(ScanRun)) == 0
        assert db.scalar(select(func.count()).select_from(ScanRunItem)) == 0
    (schedule,) = scheduler.list(actor)["items"]
    assert schedule["enabled"]
    engine.dispose()


@pytest.mark.parametrize("uploaded_first", [False, True])
def test_attachment_documents_from_the_scan_are_erased_with_their_files(
    tmp_path: Path, uploaded_first: bool
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    engine = auth.engine
    vault = PrivateSettings(engine, b"g" * 32)
    mailbox = Mailboxes(engine, vault).connect(
        actor,
        GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic")),
    )

    def respond(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if request.url.host == "oauth2.googleapis.com":
            data: dict[str, Any] = {"access_token": "synthetic-access"}
        elif path.endswith("profile"):
            data = {"emailAddress": "owner@example.test"}
        elif path.endswith("messages"):
            data = {"messages": [{"id": "abc123"}]}
        elif path.endswith("/attachments/att-photo"):
            data = {"size": len(PHOTO), "data": encoded(PHOTO)}
        elif "/attachments/" in path:
            data = {"size": len(RECEIPT), "data": encoded(RECEIPT)}
        else:
            data = message("abc123")
        return httpx2.Response(200, json=data)

    storage = files(engine)
    documents = DocumentService(engine, storage)
    if uploaded_first:
        documents.upload(actor, RECEIPT, "my-receipt.txt")
    photos = PhotoService(engine, storage)
    handler = GmailAttachmentHandler(
        engine, vault, provider(httpx2.MockTransport(respond)), documents, photos
    )
    scans = ScanService(engine, ScanRegistry([handler]))
    scope = {
        "mailbox_id": mailbox["id"],
        "from_timestamp": 100,
        "until_timestamp": 200,
        "max_messages": 5,
    }
    scans.enqueue(actor, "gmail_attachments", scope, "first")
    asyncio.run(ScanWorker(scans).run_once())
    with Session(engine) as db:
        (key,) = db.scalars(select(Document.original_key))
        picture = db.execute(select(Photo.original_key, Photo.preview_key)).one()
    photo_keys = [k for k in picture if k]
    assert key and storage.exists(key) and photo_keys
    result = erase(SourceErasure(engine, storage), actor, "mailbox", mailbox["id"])
    assert result["counts"]["documents"] == int(not uploaded_first)
    assert result["counts"]["photos"] == 1
    assert result["files"] == int(not uploaded_first) + len(photo_keys)
    with Session(engine) as db:
        remaining = db.scalar(select(func.count()).select_from(Document))
        pictures = db.scalar(select(func.count()).select_from(Photo))
        links = db.scalar(text("SELECT count(*) FROM email_attachments"))
    assert remaining == int(uploaded_first) and pictures == 0 and links == 0
    assert storage.exists(key) is uploaded_first
    assert not any(storage.exists(k) for k in photo_keys)
    engine.dispose()


@pytest.mark.usefixtures("configured_database")
def test_erasure_http_requires_a_write_session_and_the_preview_fingerprint() -> None:
    app = create_app()
    with TestClient(app) as client:
        body = {"kind": "mailbox", "id": "missing"}
        assert client.post("/api/erasure/preview", json=body).status_code == 401
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        engine: Engine = app.state.auth_store.engine
        with Session(engine) as db:
            owner = db.scalar(text("SELECT id FROM users ORDER BY created_at LIMIT 1"))
            db.add(
                Mailbox(
                    id="mailbox-1",
                    user_id=owner,
                    credential_id=None,
                    account_key="k",
                    address="alice@example.test",
                    revision=1,
                    created_at=1,
                    updated_at=1,
                )
            )
            db.commit()
        body = {"kind": "mailbox", "id": "mailbox-1"}
        no_csrf = {"Cookie": alice["Cookie"]}
        assert (
            client.post("/api/erasure/preview", headers=no_csrf, json=body).status_code
            == 403
        )
        assert (
            client.post("/api/erasure/preview", headers=bob, json=body).status_code
            == 404
        )
        assert (
            client.post(
                "/api/erasure/preview", headers=alice, json={**body, "user_id": "x"}
            ).status_code
            == 422
        )
        preview = client.post("/api/erasure/preview", headers=alice, json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json()["counts"]["connections"] == 1
        stale = {**body, "fingerprint": "0" * 64}
        assert (
            client.post("/api/erasure/erase", headers=alice, json=stale).status_code
            == 409
        )
        confirmed = {**body, "fingerprint": preview.json()["fingerprint"]}
        erased = client.post("/api/erasure/erase", headers=alice, json=confirmed)
        assert erased.status_code == 200, erased.text
        assert erased.json()["erased"] is True
        assert (
            client.post("/api/erasure/preview", headers=alice, json=body).status_code
            == 404
        )
