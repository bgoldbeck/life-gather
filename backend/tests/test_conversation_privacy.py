import json
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from database_support import database
from pydantic import ValidationError
from sqlalchemy import event, insert, select, update
from sqlalchemy.orm import Session
from stored_files import files
from test_recovery_bundle import installation

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.models import Conversation, Turn, Usage
from lifegather.chat.privacy import (
    ConversationDelete,
    ConversationPrivacy,
    ConversationToken,
)
from lifegather.chat.service import ChatService, TurnInput
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.service import DocumentService
from lifegather.memory.export import RecordExport
from lifegather.memory.models import Audit
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoService
from lifegather.scans.models import ScanRun

pytestmark = pytest.mark.usefixtures("configured_database")


def completed(
    chat: ChatService, actor: Account, conversation: str, key: str
) -> dict[str, Any]:
    turn, _ = chat.begin(
        actor,
        conversation,
        TurnInput(
            request_id=key, mode="search", text=f"EPHEMERAL private prompt {key}"
        ),
    )
    return chat.finish(actor, turn["id"], {"text": f"EPHEMERAL private reply {key}"})


def test_deletion_removes_only_owned_transcript_and_replays_without_content_tombstone(
    tmp_path: Path,
) -> None:
    case = installation(tmp_path)
    chat = ChatService(case.store.engine)
    target = chat.create(case.alice)["id"]
    other = chat.create(case.alice)["id"]
    foreign = chat.create(case.bob)["id"]
    completed(chat, case.alice, target, "target-1")
    completed(chat, case.alice, target, "target-2")
    completed(chat, case.alice, other, "other")
    completed(chat, case.bob, foreign, "foreign")
    job_id = "synthetic-retained-scan"
    with Session(case.store.engine) as scan_session, scan_session.begin():
        scan_session.add(
            ScanRun(
                id=job_id,
                user_id=case.alice.id,
                handler_key="synthetic",
                resource_key="synthetic:mail",
                config_json="{}",
                cursor_json="{}",
                request_id="retained-scan",
                fingerprint="f" * 64,
                state="queued",
                cancel_requested=False,
                scanned=0,
                imported=0,
                existing=0,
                skipped=0,
                steps=0,
                attempts=0,
                truncated=False,
                error=None,
                lease_token=None,
                lease_until=None,
                created_at=1,
                updated_at=1,
                started_at=None,
                completed_at=None,
            )
        )
    with case.store.engine.begin() as db:
        db.execute(
            insert(Usage).values(
                user_id=case.alice.id,
                day=datetime.now(UTC).date().isoformat(),
                requests=3,
                input_tokens=10,
                output_tokens=20,
            )
        )
    budget = chat.usage(case.alice)
    secret_before = PrivateSettings(case.store.engine, case.key).read_secret(
        case.alice, case.credential
    )
    before = json.loads(RecordExport(case.store.engine).download(case.alice))[
        "collections"
    ]
    service = ConversationPrivacy(case.store.engine)
    preview = service.preview(case.alice, target)
    assert preview["turn_count"] == 2 and preview["pending_count"] == 0
    assert preview["format"] == "lifegather-conversation-deletion/1"
    assert preview["id"] == target
    with pytest.raises(MemoryError):
        service.preview(case.bob, target)
    action = ConversationDelete(preview_token=preview["preview_token"], confirmed=True)
    with pytest.raises(MemoryError):
        service.delete(case.bob, target, action)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: service.delete(case.alice, target, action), range(2))
        )
    assert results == [{"id": target, "deleted": True}] * 2
    assert service.delete(case.alice, target, action) == results[0]
    with pytest.raises(MemoryError):
        service.delete(case.bob, target, action)
    assert {row["id"] for row in chat.conversations(case.alice)["items"]} == {other}
    assert (
        chat.turns(case.alice, other)["items"]
        and chat.turns(case.bob, foreign)["items"]
    )
    with pytest.raises(MemoryError):
        chat.turns(case.alice, target)
    with pytest.raises(MemoryError):
        chat.recent(case.alice, target)
    with pytest.raises(MemoryError):
        chat.begin(
            case.alice,
            target,
            TurnInput(request_id="new", mode="search", text="No resurrection"),
        )
    assert chat.usage(case.alice) == budget
    assert (
        PhotoService(case.store.engine, files(case.store.engine)).binary(
            case.alice, case.photo, True
        )[0]
        == case.photo_original
    )
    assert (
        DocumentService(case.store.engine, files(case.store.engine)).binary(
            case.bob, case.document
        )
        == case.document_original
    )
    assert (
        PrivateSettings(case.store.engine, case.key).read_secret(
            case.alice, case.credential
        )
        == secret_before
    )
    after = json.loads(RecordExport(case.store.engine).download(case.alice))[
        "collections"
    ]
    for table, rows in before.items():
        if table not in {"chat_conversations", "chat_turns", "memory_audit"}:
            assert after[table] == rows
    assert b"EPHEMERAL private prompt target" not in RecordExport(
        case.store.engine
    ).download(case.alice)
    with Session(case.store.engine) as db:
        job = db.get(ScanRun, job_id)
        assert job and job.state == "queued" and not job.cancel_requested
        audits = list(
            db.scalars(
                select(Audit).where(
                    Audit.user_id == case.alice.id,
                    Audit.operation == "conversation_deleted",
                    Audit.target_id == target,
                )
            )
        )
        assert len(audits) == 1
        assert "EPHEMERAL" not in (audits[0].provenance_json or "")
    case.store.engine.dispose()


def test_preview_uses_bounded_metadata_and_empty_conversations_can_be_deleted(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    actor = store.login("synthetic", "synthetic@example.test", "Synthetic", now=1).user
    chat = ChatService(store.engine)
    target = chat.create(actor)["id"]
    service = ConversationPrivacy(store.engine)
    empty = service.preview(actor, target)
    assert empty["turn_count"] == 0 and empty["state_counts"] == {}
    assert service.delete(
        actor,
        target,
        ConversationDelete(preview_token=empty["preview_token"], confirmed=True),
    )["deleted"]
    target = chat.create(actor)["id"]
    with store.engine.begin() as db:
        db.execute(
            insert(Turn),
            [
                {
                    "id": f"bulk-{i:04}",
                    "user_id": actor.id,
                    "conversation_id": target,
                    "request_id": f"bulk-{i}",
                    "mode": "search",
                    "text": "Synthetic private prompt" * 100,
                    "fingerprint": f"{i:064x}",
                    "state": "complete",
                    "result_json": json.dumps(
                        {"text": "Synthetic private reply" * 200}
                    ),
                    "created_at": i + 1,
                }
                for i in range(500)
            ],
        )
    statements: list[str] = []

    def observe(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        execution: Any,
        many: bool,
    ) -> None:
        statements.append(statement)

    event.listen(store.engine, "before_cursor_execute", observe)
    try:
        preview = service.preview(actor, target)
    finally:
        event.remove(store.engine, "before_cursor_execute", observe)
    assert preview["turn_count"] == 500 and preview["pending_count"] == 0
    assert len(json.dumps(preview)) < 500
    assert all(sql.startswith(("SET TRANSACTION", "SELECT")) for sql in statements)
    assert all(
        "chat_turns.text" not in sql and "chat_turns.result_json" not in sql
        for sql in statements
    )
    store.engine.dispose()


def test_privacy_http_requires_private_session_csrf_review_and_confirmation() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        owner, actor = signed_headers(app, "privacy-owner")
        foreign, foreign_actor = signed_headers(app, "privacy-foreign")
        chat = ChatService(app.state.auth_store.engine)
        target = chat.create(actor)["id"]
        pending, _ = chat.begin(
            actor,
            target,
            TurnInput(
                request_id="pending", mode="search", text="Synthetic HTTP pending"
            ),
        )
        base = f"/api/chat/conversations/{target}"
        snapshot = ConversationPrivacy(chat.engine).preview(actor, target)
        token = snapshot["preview_token"]
        for suffix, body in (
            ("deletion-preview", {}),
            ("stop-pending", {"preview_token": token}),
            ("delete", {"preview_token": token, "confirmed": True}),
        ):
            path = f"{base}/{suffix}"
            assert client.post(path, json=body).status_code == 401
            assert (
                client.post(
                    path, headers={"Cookie": owner["Cookie"]}, json=body
                ).status_code
                == 403
            )
            assert client.post(path, headers=foreign, json=body).status_code == 400
            assert (
                client.post(
                    path, headers=owner, json={**body, "user_id": foreign_actor.id}
                ).status_code
                == 422
            )
        reviewed = client.post(f"{base}/deletion-preview", headers=owner, json={})
        assert (
            reviewed.status_code == 200
            and reviewed.headers["cache-control"] == "no-store"
        )
        for invalid in (
            {"preview_token": token},
            {"preview_token": token, "confirmed": False},
            {"preview_token": token, "confirmed": "true"},
        ):
            assert (
                client.post(f"{base}/delete", headers=owner, json=invalid).status_code
                == 422
            )
        assert (
            client.post(
                f"{base}/delete",
                headers=owner,
                json={"preview_token": token, "confirmed": True},
            ).status_code
            == 400
        )
        stopped = client.post(
            f"{base}/stop-pending", headers=owner, json={"preview_token": token}
        )
        assert stopped.status_code == 200 and stopped.json()["pending_count"] == 0
        assert (
            client.post(
                f"{base}/delete",
                headers=owner,
                json={"preview_token": token, "confirmed": True},
            ).status_code
            == 409
        )
        confirmed = {
            "preview_token": stopped.json()["preview_token"],
            "confirmed": True,
        }
        deleted = client.post(f"{base}/delete", headers=owner, json=confirmed)
        assert deleted.status_code == 200 and deleted.json() == {
            "id": target,
            "deleted": True,
        }
        assert (
            client.post(f"{base}/delete", headers=owner, json=confirmed).json()
            == deleted.json()
        )
        assert client.get(f"{base}/turns", headers=owner).status_code == 400
        assert (
            client.post(
                f"{base}/turns",
                headers=owner,
                json={
                    "request_id": "new",
                    "mode": "organize",
                    "text": "Set model to Synthetic",
                },
            ).status_code
            == 400
        )
        with pytest.raises(MemoryError):
            chat.finish(actor, pending["id"], {"text": "Late completion"})


def test_stop_pending_is_separate_reviewed_and_late_finish_cannot_revive(
    tmp_path: Path,
) -> None:
    case = installation(tmp_path)
    chat = ChatService(case.store.engine)
    target = chat.create(case.alice)["id"]
    pending, _ = chat.begin(
        case.alice,
        target,
        TurnInput(request_id="pending", mode="search", text="Transient pending prompt"),
    )
    # Old pending rows display as interrupted, but still need an explicit stop.
    with case.store.engine.begin() as db:
        db.execute(update(Turn).where(Turn.id == pending["id"]).values(created_at=1))
    service = ConversationPrivacy(case.store.engine)
    preview = service.preview(case.alice, target)
    token = ConversationToken(preview_token=preview["preview_token"])
    assert preview["pending_count"] == 1
    with pytest.raises(MemoryError, match="pending"):
        service.delete(
            case.alice,
            target,
            ConversationDelete(preview_token=token.preview_token, confirmed=True),
        )
    refreshed = service.stop(case.alice, target, token)
    assert refreshed["pending_count"] == 0
    assert (
        chat.finish(case.alice, pending["id"], {"text": "Late reply"})["state"]
        == "canceled"
    )
    with pytest.raises(MemoryError, match="changed"):
        service.delete(
            case.alice,
            target,
            ConversationDelete(preview_token=token.preview_token, confirmed=True),
        )
    action = ConversationDelete(
        preview_token=refreshed["preview_token"], confirmed=True
    )
    service.delete(case.alice, target, action)
    with pytest.raises(MemoryError):
        chat.finish(case.alice, pending["id"], {"text": "Late reply"})
    with Session(case.store.engine) as db:
        assert db.scalar(select(Turn.id).where(Turn.conversation_id == target)) is None
        assert (
            db.scalar(select(Conversation.id).where(Conversation.id == target)) is None
        )
    case.store.engine.dispose()


@pytest.mark.parametrize("change", ["append", "complete", "cancel"])
def test_changed_conversation_requires_review_before_stop_or_delete(
    tmp_path: Path, change: str
) -> None:
    case = installation(tmp_path)
    chat = ChatService(case.store.engine)
    target = chat.create(case.alice)["id"]
    turn, _ = chat.begin(
        case.alice,
        target,
        TurnInput(request_id="pending", mode="search", text="Transient prompt"),
    )
    if change == "append":
        chat.finish(case.alice, turn["id"], {"text": "Done"})
    service = ConversationPrivacy(case.store.engine)
    preview = service.preview(case.alice, target)
    if change == "append":
        completed(chat, case.alice, target, "appended")
    elif change == "complete":
        chat.finish(case.alice, turn["id"], {"text": "Done"})
    else:
        chat.cancel(case.alice, "pending")
    with pytest.raises(MemoryError, match="changed"):
        service.stop(
            case.alice,
            target,
            ConversationToken(preview_token=preview["preview_token"]),
        )
    with pytest.raises(MemoryError, match="changed"):
        service.delete(
            case.alice,
            target,
            ConversationDelete(preview_token=preview["preview_token"], confirmed=True),
        )
    assert chat.turns(case.alice, target)["items"]
    case.store.engine.dispose()


def test_confirmation_revalidation_and_atomic_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = installation(tmp_path)
    chat = ChatService(case.store.engine)
    target = chat.create(case.alice)["id"]
    completed(chat, case.alice, target, "retained-on-failure")
    service = ConversationPrivacy(case.store.engine)
    preview = service.preview(case.alice, target)
    action = ConversationDelete(preview_token=preview["preview_token"], confirmed=True)
    with pytest.raises(ValidationError):
        service.delete(
            case.alice, target, action.model_copy(update={"confirmed": False})
        )
    with pytest.raises(ValidationError):
        ConversationDelete.model_validate(
            {
                "preview_token": preview["preview_token"],
                "confirmed": True,
                "user_id": case.bob.id,
            }
        )

    def failed_audit(*args: Any, **kwargs: Any) -> None:
        raise MemoryError("Synthetic audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(MemoryService, "_audit", failed_audit)
        with pytest.raises(MemoryError, match="audit failure"):
            service.delete(case.alice, target, action)
    assert len(chat.turns(case.alice, target)["items"]) == 1
    assert service.preview(case.alice, target)["preview_token"] == action.preview_token
    case.store.engine.dispose()


def test_completion_and_reviewed_stop_cannot_both_claim_success(tmp_path: Path) -> None:
    case = installation(tmp_path)
    chat = ChatService(case.store.engine)
    target = chat.create(case.alice)["id"]
    turn, _ = chat.begin(
        case.alice,
        target,
        TurnInput(request_id="race", mode="search", text="Synthetic pending race"),
    )
    service = ConversationPrivacy(case.store.engine)
    token = ConversationToken(
        preview_token=service.preview(case.alice, target)["preview_token"]
    )
    read_ready, release_read = threading.Event(), threading.Event()
    worker = threading.local()

    def pause_finish_read(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        execution: Any,
        many: bool,
    ) -> None:
        if getattr(worker, "finishing", False) and statement.startswith(
            "SELECT chat_turns.id"
        ):
            read_ready.set()
            assert release_read.wait(timeout=5)

    def finish() -> dict[str, Any]:
        worker.finishing = True
        return chat.finish(
            case.alice, turn["id"], {"text": "Synthetic late completion"}
        )

    event.listen(case.store.engine, "after_cursor_execute", pause_finish_read)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            finishing = pool.submit(finish)
            assert read_ready.wait(timeout=5)
            stopping = pool.submit(service.stop, case.alice, target, token)
            try:
                stopping.result(timeout=1)
            except FutureTimeout:
                pass
            finally:
                release_read.set()
            result = finishing.result(timeout=5)
            try:
                stopped = stopping.result(timeout=5)
            except MemoryError as error:
                assert "changed" in str(error) and result["state"] == "complete"
            else:
                assert stopped["pending_count"] == 0 and result["state"] == "canceled"
    finally:
        release_read.set()
        event.remove(case.store.engine, "after_cursor_execute", pause_finish_read)
        case.store.engine.dispose()
