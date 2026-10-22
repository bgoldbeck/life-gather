import os
import stat
from pathlib import Path
from typing import Any

import pytest
from database_support import database
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_photos import image_bytes

from lifegather.auth.store import Account, AuthStore
from lifegather.config import Settings
from lifegather.documents.models import Document
from lifegather.documents.service import DocumentDelete, DocumentService
from lifegather.main import create_app
from lifegather.memory.service import MemoryError
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoDelete, PhotoService
from lifegather.storage import (
    LocalStorage,
    ObjectNotFound,
    ObjectStorage,
    S3Storage,
    StorageError,
    storage_from_settings,
)
from lifegather.storage.originals import move_inline_originals


class MissingKey(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "NoSuchKey"}}


class Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        pass


class FakeS3:
    """In-memory stand-in for the boto3 S3 client calls the backend makes."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> None:
        self.objects[kwargs["Bucket"], kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs: Any) -> dict[str, Body]:
        try:
            return {"Body": Body(self.objects[kwargs["Bucket"], kwargs["Key"]])}
        except KeyError:
            raise MissingKey() from None

    def delete_object(self, **kwargs: Any) -> None:
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    def head_object(self, **kwargs: Any) -> None:
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise MissingKey()


@pytest.fixture(params=["local", "s3"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> ObjectStorage:
    if request.param == "local":
        return LocalStorage(tmp_path / "files")
    return S3Storage(FakeS3(), "private-bucket", "/lifegather/")


def test_backends_share_one_contract(storage: ObjectStorage) -> None:
    key = "users/u-1/documents/d-1/original"
    assert not storage.exists(key)
    with pytest.raises(ObjectNotFound):
        storage.get(key)
    storage.save(b"first", key)
    storage.save(b"synthetic bytes", key)
    assert storage.exists(key) and storage.get(key) == b"synthetic bytes"
    storage.delete(key)
    storage.delete(key)
    assert not storage.exists(key)
    for unsafe in ("../escape", "/absolute", "a//b", "a/../b", "Upper", "", "a/.b"):
        with pytest.raises(StorageError):
            storage.save(b"x", unsafe)


def test_local_files_are_private_and_s3_keys_use_the_prefix(tmp_path: Path) -> None:
    local = LocalStorage(tmp_path / "files")
    local.save(b"synthetic", "users/u/photos/p/original")
    path = tmp_path / "files" / "users" / "u" / "photos" / "p" / "original"
    assert path.read_bytes() == b"synthetic"
    if os.name != "nt":  # Windows ignores POSIX permission bits
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["original"]
    client = FakeS3()
    S3Storage(client, "bucket", "tenant").save(b"x", "a/b")
    assert list(client.objects) == [("bucket", "tenant/a/b")]


def test_storage_settings_choose_the_backend(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    assert settings.files_dir == tmp_path / "data" / "files"
    local = storage_from_settings(settings)
    assert isinstance(local, LocalStorage) and local.root == settings.files_dir
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(storage_backend="s3")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(
            storage_backend="s3",
            s3_bucket="b",
            s3_endpoint_url="http://storage.example.test",
        )
    configured = Settings(storage_backend="s3", s3_bucket="private")
    try:
        import boto3  # type: ignore[import-not-found,unused-ignore]  # noqa: F401
    except ImportError:
        with pytest.raises(StorageError, match="s3"):
            storage_from_settings(configured)


def accounts(tmp_path: Path) -> tuple[AuthStore, Account]:
    store = AuthStore(database(tmp_path / "data"))
    store.migrate()
    return store, store.login("alice", "a@example.test", "Alice", now=1).user


def test_originals_live_only_in_storage_and_deletion_removes_them(
    tmp_path: Path,
) -> None:
    store, alice = accounts(tmp_path)
    storage = files(store.engine)
    documents = DocumentService(store.engine, storage)
    photos = PhotoService(store.engine, storage)
    pdf, image = synthetic_pdf(), image_bytes()
    document = documents.upload(alice, pdf, "synthetic.pdf")
    photo = photos.upload(alice, image, "synthetic.jpg")
    with Session(store.engine) as db:
        doc_row = db.get(Document, document["id"])
        photo_row = db.get(Photo, photo["id"])
        assert doc_row and photo_row
        assert doc_row.original is None and photo_row.original is None
        assert photo_row.preview is None
        doc_key, photo_keys = (
            doc_row.original_key,
            (photo_row.original_key, photo_row.preview_key),
        )
    assert doc_key == f"users/{alice.id}/documents/{document['id']}/original"
    assert doc_key and storage.get(doc_key) == pdf
    assert photo_keys[0] and storage.get(photo_keys[0]) == image
    assert documents.binary(alice, document["id"]) == pdf
    assert photos.binary(alice, photo["id"], True)[0] == image
    assert photos.binary(alice, photo["id"])[0] == storage.get(photo_keys[1] or "")

    # Tampered or missing bytes are never served as evidence.
    storage.save(b"tampered", doc_key)
    with pytest.raises(MemoryError, match="unavailable"):
        documents.binary(alice, document["id"])
    storage.save(pdf, doc_key)

    documents.delete(
        alice,
        DocumentDelete(
            document_id=document["id"], expected_updated_at=document["updated_at"]
        ),
    )
    photos.delete(
        alice,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=photo["updated_at"]),
    )
    assert not storage.exists(doc_key)
    assert not any(storage.exists(key or "") for key in photo_keys)
    with Session(store.engine) as db:
        assert db.scalar(select(Document.original_key)) is None
        assert db.scalar(select(Photo.original_key)) is None
    with pytest.raises(MemoryError):
        documents.binary(alice, document["id"])


class BrokenDelete(LocalStorage):
    def delete(self, key: str) -> None:
        raise StorageError("Unable to delete the stored file")


def test_failed_object_delete_is_retried_on_startup(tmp_path: Path) -> None:
    store, alice = accounts(tmp_path)
    broken = BrokenDelete(tmp_path / "data" / "files")
    documents = DocumentService(store.engine, broken)
    document = documents.upload(alice, synthetic_pdf(), "synthetic.pdf")
    documents.delete(
        alice,
        DocumentDelete(
            document_id=document["id"], expected_updated_at=document["updated_at"]
        ),
    )
    with Session(store.engine) as db:
        key = db.scalar(select(Document.original_key))
    assert key and broken.exists(key)
    move_inline_originals(store.engine, files(store.engine))
    assert not broken.exists(key)
    with Session(store.engine) as db:
        assert db.scalar(select(Document.original_key)) is None


def test_upload_rollback_leaves_no_stored_object(tmp_path: Path) -> None:
    store, alice = accounts(tmp_path)
    storage = files(store.engine)
    photos = PhotoService(store.engine, storage)
    with pytest.raises(MemoryError):
        photos.upload(alice, image_bytes(), "synthetic.jpg", asset_id="missing")
    assert not (tmp_path / "data" / "files").exists() or not any(
        path.is_file() for path in (tmp_path / "data" / "files").rglob("*")
    )
    with pytest.raises(MemoryError, match="not configured"):
        PhotoService(store.engine).upload(alice, image_bytes(), "synthetic.jpg")


def make_legacy(store: AuthStore, storage: ObjectStorage) -> None:
    """Rewrite rows to the pre-0028 shape: bytes inline, no keys, no files."""
    with Session(store.engine) as db:
        for document in db.scalars(select(Document)):
            assert document.original_key
            document.original = storage.get(document.original_key)
            storage.delete(document.original_key)
            document.original_key = None
        for photo in db.scalars(select(Photo)):
            assert photo.original_key and photo.preview_key
            photo.original = storage.get(photo.original_key)
            photo.preview = storage.get(photo.preview_key)
            storage.delete(photo.original_key)
            storage.delete(photo.preview_key)
            photo.original_key = photo.preview_key = None
        db.commit()


def test_existing_inline_originals_keep_working_and_move_on_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(data))
    store, alice = accounts(tmp_path)
    storage = files(store.engine)
    pdf, image = synthetic_pdf(), image_bytes()
    document = DocumentService(store.engine, storage).upload(alice, pdf, "s.pdf")
    photo = PhotoService(store.engine, storage).upload(alice, image, "s.jpg")
    make_legacy(store, storage)
    assert not any(path.is_file() for path in (data / "files").rglob("*"))
    # Legacy rows are still served from the database before they move.
    assert DocumentService(store.engine, storage).binary(alice, document["id"]) == pdf
    assert PhotoService(store.engine).binary(alice, photo["id"], True)[0] == image
    store.engine.dispose()

    with TestClient(create_app()) as client:
        engine = client.app.state.auth_store.engine  # type: ignore[attr-defined]
        with Session(engine) as db:
            row = db.get(Document, document["id"])
            picture = db.get(Photo, photo["id"])
            assert row and picture
            assert row.original is None and row.original_key
            assert picture.original is None and picture.preview is None
            assert picture.original_key and picture.preview_key
        assert storage.get(row.original_key) == pdf
        assert storage.get(picture.original_key) == image
        assert (
            DocumentService(engine, client.app.state.object_storage).binary(  # type: ignore[attr-defined]
                alice, document["id"]
            )
            == pdf
        )
        # A second pass finds nothing left to move.
        assert move_inline_originals(engine, storage) == 0


def test_legacy_move_refuses_corrupt_inline_bytes(tmp_path: Path) -> None:
    store, alice = accounts(tmp_path)
    storage = files(store.engine)
    DocumentService(store.engine, storage).upload(alice, synthetic_pdf(), "s.pdf")
    make_legacy(store, storage)
    with store.engine.begin() as db:
        db.execute(text("UPDATE documents SET original = '\\x00'::bytea"))
    assert move_inline_originals(store.engine, storage) == 0
    with Session(store.engine) as db:
        row = db.scalar(select(Document))
        assert row and row.original == b"\x00" and row.original_key is None
