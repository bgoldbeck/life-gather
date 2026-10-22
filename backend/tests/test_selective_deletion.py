import asyncio
import time
from io import BytesIO
from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from stored_files import files
from test_conversation_privacy import completed
from test_documents import synthetic_pdf
from test_mcp_http import signed_headers
from test_photos import image_bytes

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.models import Conversation, Turn
from lifegather.chat.retention import (
    DAY,
    ConversationRetention,
    RetentionInput,
    retention_sweeps,
)
from lifegather.chat.service import ChatService, TurnInput
from lifegather.documents.models import Document
from lifegather.documents.service import (
    DocumentDelete,
    DocumentDeleteMany,
    DocumentService,
)
from lifegather.main import create_app
from lifegather.memory.models import Audit
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoDelete, PhotoDeleteMany, PhotoService


def accounts(tmp_path: Path) -> tuple[AuthStore, Account, Account]:
    store = AuthStore(database(tmp_path / "data"))
    store.migrate()
    alice = store.login("alice", "a@example.test", "Alice", now=1).user
    bob = store.login("bob", "b@example.test", "Bob", now=1).user
    return store, alice, bob


def picture(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (120, 80), color).save(output, "JPEG")
    return output.getvalue()


def stored(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data" / "files"
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def operations(store: AuthStore, operation: str) -> list[str]:
    with Session(store.engine) as db:
        return list(
            db.scalars(select(Audit.target_id).where(Audit.operation == operation))
        )


def test_photos_delete_together_and_remove_stored_files(tmp_path: Path) -> None:
    store, alice, _ = accounts(tmp_path)
    photos = PhotoService(store.engine, files(store.engine))
    first = photos.upload(alice, image_bytes(), "first.jpg")
    second = photos.upload(alice, picture("blue"), "second.jpg")
    kept = photos.upload(alice, picture("green"), "kept.jpg")
    assert len(stored(tmp_path)) == 6
    request = PhotoDeleteMany(
        photos=[
            PhotoDelete(photo_id=row["id"], expected_updated_at=row["updated_at"])
            for row in (first, second)
        ]
    )
    result = photos.delete_many(alice, request)
    assert result["deleted_count"] == 2
    assert all(row["deleted_at"] is not None for row in result["photos"])
    # Original and preview of the kept photo are the only stored files left.
    assert len(stored(tmp_path)) == 2
    with Session(store.engine) as db:
        rows = {row.id: row for row in db.scalars(select(Photo))}
        assert rows[first["id"]].original_key is None
        assert rows[second["id"]].preview_key is None
        assert rows[kept["id"]].deleted_at is None
    assert sorted(operations(store, "photo_deleted")) == sorted(
        [first["id"], second["id"]]
    )
    # A repeated request is a safe replay with no second receipt.
    assert photos.delete_many(alice, request)["deleted_count"] == 2
    assert len(operations(store, "photo_deleted")) == 2


def test_stale_or_foreign_item_refuses_the_whole_batch(tmp_path: Path) -> None:
    store, alice, bob = accounts(tmp_path)
    storage = files(store.engine)
    documents = DocumentService(store.engine, storage)
    mine = documents.upload(alice, synthetic_pdf(), "mine.pdf")
    other = documents.upload(alice, synthetic_pdf("Second synthetic"), "other.pdf")
    foreign = documents.upload(bob, synthetic_pdf("Bob synthetic"), "bob.pdf")
    before = stored(tmp_path)

    def batch(*items: tuple[str, int]) -> DocumentDeleteMany:
        return DocumentDeleteMany(
            documents=[
                DocumentDelete(document_id=identifier, expected_updated_at=version)
                for identifier, version in items
            ]
        )

    with pytest.raises(NoteConflict):
        documents.delete_many(
            alice,
            batch((mine["id"], mine["updated_at"]), (other["id"], 0)),
        )
    with pytest.raises(MemoryError, match="not found"):
        documents.delete_many(
            alice,
            batch(
                (mine["id"], mine["updated_at"]),
                (foreign["id"], foreign["updated_at"]),
            ),
        )
    with pytest.raises(MemoryError, match="only once"):
        documents.delete_many(
            alice,
            batch((mine["id"], mine["updated_at"]), (mine["id"], mine["updated_at"])),
        )
    assert stored(tmp_path) == before
    with Session(store.engine) as db:
        assert db.scalars(select(Document.deleted_at)).all() == [None, None, None]
    assert operations(store, "document_deleted") == []

    result = documents.delete_many(
        alice,
        batch((mine["id"], mine["updated_at"]), (other["id"], other["updated_at"])),
    )
    assert result["deleted_count"] == 2
    assert "extracted_text" not in result["documents"][0]
    with Session(store.engine) as db:
        rows = {row.id: row for row in db.scalars(select(Document))}
        assert rows[mine["id"]].extracted_text == ""
        assert rows[mine["id"]].original_key is None
        assert rows[foreign["id"]].deleted_at is None
        assert rows[foreign["id"]].original_key
    assert len(stored(tmp_path)) == 1


def test_batches_are_bounded() -> None:
    with pytest.raises(ValidationError):
        PhotoDeleteMany(photos=[])
    with pytest.raises(ValidationError):
        PhotoDeleteMany(
            photos=[
                PhotoDelete(photo_id=f"p-{n}", expected_updated_at=0) for n in range(51)
            ]
        )


def age(store: AuthStore, conversation: str, days: int) -> None:
    then = time.time_ns() // 1000 - days * DAY
    with Session(store.engine) as db, db.begin():
        db.execute(
            update(Conversation)
            .where(Conversation.id == conversation)
            .values(created_at=then)
        )
        db.execute(
            update(Turn)
            .where(Turn.conversation_id == conversation)
            .values(created_at=then)
        )


def test_retention_removes_only_expired_owned_idle_conversations(
    tmp_path: Path,
) -> None:
    store, alice, bob = accounts(tmp_path)
    chat = ChatService(store.engine)
    old = chat.create(alice)["id"]
    completed(chat, alice, old, "old")
    recent = chat.create(alice)["id"]
    completed(chat, alice, recent, "recent")
    empty = chat.create(alice)["id"]
    busy = chat.create(alice)["id"]
    chat.begin(alice, busy, TurnInput(request_id="busy", mode="search", text="Pending"))
    foreign = chat.create(bob)["id"]
    for conversation in (old, empty, busy, foreign):
        age(store, conversation, 40)
    age(store, recent, 10)

    retention = ConversationRetention(store.engine)
    assert retention.days(alice) is None
    assert retention.sweep() == 0
    assert retention.preview(alice, 30)["eligible_count"] == 2
    assert retention.preview(alice, 90)["eligible_count"] == 0

    result = retention.update(alice, RetentionInput(conversation_days=30))
    assert result == {"conversation_days": 30, "deleted_count": 2}
    assert retention.days(alice) == 30 and retention.days(bob) is None
    with Session(store.engine) as db:
        remaining = set(db.scalars(select(Conversation.id)))
        turns = set(db.scalars(select(Turn.conversation_id)))
    assert remaining == {recent, busy, foreign}
    assert old not in turns
    assert sorted(operations(store, "conversation_deleted")) == sorted([old, empty])

    # Once the pending request finishes and time passes, the sweep removes it.
    with Session(store.engine) as db, db.begin():
        db.execute(
            update(Turn).where(Turn.conversation_id == busy).values(state="done")
        )
    assert retention.sweep() == 1
    assert retention.sweep() == 0

    assert retention.update(alice, RetentionInput(conversation_days=None)) == {
        "conversation_days": None,
        "deleted_count": 0,
    }
    age(store, recent, 400)
    assert retention.sweep() == 0
    with pytest.raises(ValidationError):
        RetentionInput.model_validate({"conversation_days": 7})


def test_retention_sweeps_run_until_cancelled(tmp_path: Path) -> None:
    store, alice, _ = accounts(tmp_path)
    chat = ChatService(store.engine)
    ConversationRetention(store.engine).update(
        alice, RetentionInput(conversation_days=30)
    )
    old = chat.create(alice)["id"]
    age(store, old, 31)

    async def run() -> None:
        task = asyncio.create_task(retention_sweeps(store.engine, interval=0.01))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if operations(store, "conversation_deleted"):
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert operations(store, "conversation_deleted") == [old]


def test_http_adapters_require_session_csrf_and_strict_bodies() -> None:
    app = create_app()
    with TestClient(app) as client:
        owner, actor = signed_headers(app, "retention-owner")
        photos = PhotoService(app.state.auth_store.engine, app.state.object_storage)
        photo = photos.upload(actor, image_bytes(), "synthetic.jpg")
        body = {
            "photos": [
                {"photo_id": photo["id"], "expected_updated_at": photo["updated_at"]}
            ]
        }
        assert client.post("/api/photos/delete-many", json=body).status_code == 401
        assert (
            client.post(
                "/api/photos/delete-many",
                headers={"Cookie": owner["Cookie"]},
                json=body,
            ).status_code
            == 403
        )
        response = client.post("/api/photos/delete-many", headers=owner, json=body)
        assert response.status_code == 200 and response.json()["deleted_count"] == 1
        assert (
            client.post(
                "/api/documents/delete-many",
                headers=owner,
                json={"documents": [], "user_id": "x"},
            ).status_code
            == 422
        )

        read = client.get("/api/chat/retention", headers=owner)
        assert read.status_code == 200
        assert read.json() == {
            "conversation_days": None,
            "preview": {"conversation_days": None, "eligible_count": 0},
        }
        preview = client.get("/api/chat/retention?preview_days=90", headers=owner)
        assert preview.json()["preview"] == {
            "conversation_days": 90,
            "eligible_count": 0,
        }
        assert (
            client.get("/api/chat/retention?preview_days=7", headers=owner).status_code
            == 422
        )
        assert (
            client.put(
                "/api/chat/retention",
                headers={"Cookie": owner["Cookie"]},
                json={"conversation_days": 30},
            ).status_code
            == 403
        )
        saved = client.put(
            "/api/chat/retention", headers=owner, json={"conversation_days": 365}
        )
        assert saved.json() == {"conversation_days": 365, "deleted_count": 0}
        assert (
            client.put(
                "/api/chat/retention", headers=owner, json={"conversation_days": "30"}
            ).status_code
            == 422
        )
