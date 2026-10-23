"""Per-account stored-file usage and the optional account-wide storage limit."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_personal_restore import png, rich_archive, target
from test_photos import image_bytes

from lifegather.config import Settings
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.memory.restore import PersonalRestore, RestoreConflict
from lifegather.memory.service import MemoryError
from lifegather.photos.service import PhotoDelete, PhotoService
from lifegather.storage.local import LocalStorage
from lifegather.storage.quota import account_limit, account_usage
from lifegather.storage.settings import storage_from_settings


def limited(storage: LocalStorage, limit: int) -> LocalStorage:
    return LocalStorage(storage.root, limit)


def stored_keys(root: Path, user_id: str) -> list[Path]:
    return [p for p in (root / "users" / user_id).rglob("*") if p.is_file()]


def test_quota_setting_defaults_to_no_limit_and_reaches_storage(
    tmp_path: Path,
) -> None:
    assert Settings().storage_quota_mb == 0
    assert account_limit(storage_from_settings(Settings(data_dir=tmp_path))) == 0
    configured = storage_from_settings(Settings(data_dir=tmp_path, storage_quota_mb=5))
    assert account_limit(configured) == 5 * 1024 * 1024
    with pytest.raises(ValueError):
        Settings(storage_quota_mb=-1)


def test_usage_counts_only_live_files_of_the_account() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000).user
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000).user
        storage = files(store.engine)
        photos = PhotoService(store.engine, storage)
        kept = photos.upload(alice, image_bytes(), "kept.jpg")
        removed = photos.upload(alice, png(), "removed.png")
        photos.delete(
            alice,
            PhotoDelete(
                photo_id=removed["id"], expected_updated_at=removed["updated_at"]
            ),
        )
        raw = synthetic_pdf()
        DocumentService(store.engine, storage).upload(alice, raw, "manual.pdf")
        DocumentService(store.engine, storage).upload(
            bob, synthetic_pdf("Other"), "other.pdf"
        )
        with Session(store.engine) as db:
            usage = account_usage(db, alice.id)
        assert usage["photos"] == 1 and usage["documents"] == 1
        assert usage["photo_bytes"] > kept["size"]
        assert usage["document_bytes"] == len(raw)
        assert usage["used_bytes"] == usage["photo_bytes"] + len(raw)
        on_disk = sum(p.stat().st_size for p in stored_keys(storage.root, alice.id))
        assert on_disk == usage["used_bytes"]


def test_uploads_past_the_limit_are_refused_and_store_nothing() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000).user
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000).user
        first, second = synthetic_pdf("First"), synthetic_pdf("Second")
        storage = limited(files(store.engine), len(first) + len(second) - 1)
        documents = DocumentService(store.engine, storage)
        documents.upload(alice, first, "first.pdf")
        before = stored_keys(storage.root, alice.id)
        with pytest.raises(MemoryError, match="storage is full"):
            documents.upload(alice, second, "second.pdf")
        # The same file again is a duplicate, not new storage.
        assert documents.upload(alice, first, "again.pdf")["filename"] == "first.pdf"
        with pytest.raises(MemoryError, match="storage is full"):
            PhotoService(store.engine, storage).upload(alice, image_bytes(), "a.jpg")
        assert stored_keys(storage.root, alice.id) == before
        # Each account has its own allowance.
        documents.upload(bob, second, "second.pdf")
        unlimited = DocumentService(store.engine, files(store.engine))
        unlimited.upload(alice, second, "second.pdf")


def test_usage_endpoint_reports_limit_and_requires_sign_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/storage/usage").status_code == 401
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000)
        DocumentService(store.engine, files(store.engine)).upload(
            bob.user, synthetic_pdf(), "bob.pdf"
        )
        client.cookies.set("lifegather_session", alice.token)
        body = client.get("/api/storage/usage").json()
        assert body["used_bytes"] == 0 and body["documents"] == 0
        assert body["limit_bytes"] is None and body["available_bytes"] is None
    monkeypatch.setenv("LIFEGATHER_STORAGE_QUOTA_MB", "1")
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000)
        client.cookies.set("lifegather_session", alice.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
            "X-File-Name": "manual.pdf",
        }
        raw = synthetic_pdf()
        assert (
            client.post("/api/documents", content=raw, headers=headers).status_code
            == 201
        )
        body = client.get("/api/storage/usage").json()
        assert body["limit_bytes"] == 1024 * 1024
        assert body["used_bytes"] == len(raw)
        assert body["available_bytes"] == 1024 * 1024 - len(raw)
        storage = client.app.state.object_storage  # type: ignore[attr-defined]
        storage.account_quota_bytes = len(raw) + 10
        refused = client.post(
            "/api/documents",
            content=synthetic_pdf("Another"),
            headers=headers,
        )
        assert refused.status_code == 400
        assert "storage is full" in refused.json()["detail"]


def test_restore_past_the_limit_is_refused_with_nothing_saved(
    tmp_path: Path,
) -> None:
    _, raw = rich_archive(tmp_path)
    store, actor = target(tmp_path)
    storage = limited(files(store.engine), 100)
    with pytest.raises(RestoreConflict, match="storage limit"):
        PersonalRestore(store.engine, storage).restore(actor, raw)
    assert not stored_keys(storage.root, actor.id)
    with Session(store.engine) as db:
        assert account_usage(db, actor.id)["used_bytes"] == 0
    result = PersonalRestore(store.engine, limited(storage, 1 << 30)).restore(
        actor, raw
    )
    assert result["originals"] == 2
