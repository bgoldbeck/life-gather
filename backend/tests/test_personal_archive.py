import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_STORED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, event, text
from test_documents import synthetic_pdf
from test_photos import image_bytes
from test_recovery_bundle import installation

from lifegather.auth.store import Account, AuthStore
from lifegather.documents.service import DocumentDelete, DocumentService
from lifegather.main import create_app
from lifegather.memory import archive as archives
from lifegather.memory import export as exports
from lifegather.memory.archive import ArchiveError, PersonalArchive
from lifegather.memory.export import ExportLimitError, RecordExport
from lifegather.memory.service import MemoryError
from lifegather.photos.service import PhotoService
from lifegather.profiles.service import ProfileChange, ProfileService


@dataclass
class Files:
    store: AuthStore
    actor: Account
    photo: dict[str, Any]
    document: dict[str, Any]
    image: bytes
    pdf: bytes


def files(tmp_path: Path) -> Files:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    actor = store.login("synthetic", "synthetic@example.test", "Synthetic", now=1).user
    image, pdf = image_bytes(), synthetic_pdf()
    return Files(
        store,
        actor,
        PhotoService(store.engine).upload(actor, image, "synthetic.jpg"),
        DocumentService(store.engine).upload(actor, pdf, "synthetic.pdf"),
        image,
        pdf,
    )


def unpack(raw: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    with ZipFile(BytesIO(raw)) as package:
        assert package.testzip() is None
        assert len(package.namelist()) == len(set(package.namelist()))
        assert all(info.compress_type == ZIP_STORED for info in package.infolist())
        content = {name: package.read(name) for name in package.namelist()}
    return (
        json.loads(content["manifest.json"]),
        json.loads(content["records.json"]),
        content,
    )


def test_owned_archive_preserves_originals_history_money_units_and_customs(
    tmp_path: Path,
) -> None:
    case = installation(tmp_path)
    document = DocumentService(case.store.engine).upload(
        case.alice, case.document_original, "owner-document.pdf"
    )
    custom = ProfileService(case.store.engine).save(
        case.alice,
        ProfileChange(
            entity_id=case.primary,
            field="custom",
            custom_name="Tire size",
            value="205/55R16",
            text="Synthetic label: 205/55R16.",
            operation_key="custom",
        ),
    )
    with case.store.engine.begin() as db:
        db.execute(
            text("UPDATE documents SET filename=:name WHERE id=:id"),
            {"name": "../../private/escape.pdf", "id": document["id"]},
        )
        ciphertext = db.exec_driver_sql(
            "SELECT ciphertext FROM credentials WHERE id=?", (case.credential,)
        ).scalar_one()
    raw = PersonalArchive(case.store.engine).download(case.alice)
    manifest, records, content = unpack(raw)
    assert manifest["format"] == "lifegather-personal-archive/1"
    assert records["format"] == "lifegather-records/2"
    assert manifest["snapshot_at"] == records["snapshot_at"]
    assert (
        manifest["records"]["sha256"]
        == hashlib.sha256(content["records.json"]).hexdigest()
    )
    assert manifest["records"]["size"] == len(content["records.json"])
    assert (
        records["collections"]
        == json.loads(RecordExport(case.store.engine).download(case.alice))[
            "collections"
        ]
    )
    assert custom.id.encode() in content["records.json"]
    assert b'"total_minor":1200' in content["records.json"]
    assert b'"currency":"JPY"' in content["records.json"]
    assert len(case.units) == 3
    expected = {case.photo: case.photo_original, document["id"]: case.document_original}
    assert len(manifest["originals"]) == 2
    for entry in manifest["originals"]:
        original = content[entry["path"]]
        assert original == expected[entry["id"]]
        assert entry["size"] == len(original)
        assert entry["sha256"] == hashlib.sha256(original).hexdigest()
        assert re.fullmatch(
            r"originals/(photos|documents)/[a-f0-9]{32}\.(jpg|pdf)", entry["path"]
        )
    assert set(content) == {
        "manifest.json",
        "records.json",
        *(entry["path"] for entry in manifest["originals"]),
    }
    for forbidden in (
        case.document.encode(),
        case.credential.encode(),
        case.key,
        ciphertext,
        b"Synthetic ${DO_NOT_EXPAND}",
    ):
        assert forbidden not in raw
    assert any(
        entry["original_filename"] == "../../private/escape.pdf"
        for entry in manifest["originals"]
    )


def test_archive_does_not_resurrect_deleted_originals(tmp_path: Path) -> None:
    case = files(tmp_path)
    DocumentService(case.store.engine).delete(
        case.actor,
        DocumentDelete(
            document_id=case.document["id"],
            expected_updated_at=case.document["updated_at"],
        ),
    )
    manifest, records, _ = unpack(
        PersonalArchive(case.store.engine).download(case.actor)
    )
    assert [entry["id"] for entry in manifest["originals"]] == [case.photo["id"]]
    assert case.document["id"] in [
        row["id"] for row in records["collections"]["documents"]
    ]


@pytest.mark.parametrize("table", ["photos", "documents"])
@pytest.mark.parametrize("corruption", ["hash", "missing", "length"])
def test_archive_refuses_unverifiable_active_originals(
    tmp_path: Path,
    table: str,
    corruption: str,
) -> None:
    case = files(tmp_path)
    change = {
        "hash": "content_hash='" + "0" * 64 + "'",
        "missing": "original=NULL",
        "length": "size=size+1",
    }[corruption]
    with case.store.engine.begin() as db:
        db.execute(text(f"UPDATE {table} SET {change}"))
    with pytest.raises(ArchiveError):
        PersonalArchive(case.store.engine).download(case.actor)
    # The failed download released its read transaction and changed no records.
    with case.store.engine.begin() as db:
        assert db.scalar(text("SELECT count(*) FROM photos")) == 1


@pytest.mark.parametrize("limit", ["originals", "archive", "records", "json"])
def test_archive_limits_refuse_partial_and_release_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
) -> None:
    case = files(tmp_path)
    target, name, bound = {
        "originals": (archives, "MAX_ORIGINALS", 1),
        "archive": (archives, "MAX_ARCHIVE_BYTES", 100),
        "records": (exports, "MAX_RECORDS", 1),
        "json": (exports, "MAX_BYTES", 100),
    }[limit]
    monkeypatch.setattr(target, name, bound)
    with pytest.raises(ExportLimitError):
        PersonalArchive(case.store.engine).download(case.actor)
    with case.store.engine.begin() as db:
        assert db.scalar(text("SELECT count(*) FROM documents")) == 1


def test_archive_byte_limit_includes_zip_closing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = files(tmp_path)
    complete = PersonalArchive(case.store.engine).download(case.actor)
    monkeypatch.setattr(archives, "MAX_ARCHIVE_BYTES", len(complete) - 50)
    with pytest.raises(ExportLimitError):
        PersonalArchive(case.store.engine).download(case.actor)


def test_records_and_originals_share_one_snapshot_during_concurrent_deletion(
    tmp_path: Path,
) -> None:
    case = files(tmp_path)
    changed = False

    def delete_after_metadata(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        nonlocal changed
        if not changed and statement.startswith("SELECT documents.id,"):
            changed = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(
                    DocumentService(case.store.engine).delete,
                    case.actor,
                    DocumentDelete(
                        document_id=case.document["id"],
                        expected_updated_at=case.document["updated_at"],
                    ),
                ).result(timeout=5)

    event.listen(case.store.engine, "after_cursor_execute", delete_after_metadata)
    try:
        manifest, records, content = unpack(
            PersonalArchive(case.store.engine).download(case.actor)
        )
    finally:
        event.remove(case.store.engine, "after_cursor_execute", delete_after_metadata)
    assert changed
    entry = next(
        item for item in manifest["originals"] if item["id"] == case.document["id"]
    )
    assert content[entry["path"]] == case.pdf
    assert records["collections"]["documents"][0]["deleted_at"] is None
    with pytest.raises(MemoryError):
        DocumentService(case.store.engine).binary(case.actor, case.document["id"])
    later, _, _ = unpack(PersonalArchive(case.store.engine).download(case.actor))
    assert all(item["id"] != case.document["id"] for item in later["originals"])


def test_empty_archive_is_valid_and_download_executes_only_reads(
    tmp_path: Path,
) -> None:
    case = files(tmp_path)
    empty = case.store.login("empty", "empty@example.test", "Synthetic", now=1).user
    statements: list[str] = []

    def observe(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(case.store.engine, "before_cursor_execute", observe)
    try:
        manifest, records, content = unpack(
            PersonalArchive(case.store.engine).download(empty)
        )
    finally:
        event.remove(case.store.engine, "before_cursor_execute", observe)
    assert manifest["originals"] == [] and records["total_records"] == 0
    assert set(content) == {"records.json", "manifest.json"}
    assert all(statement.startswith(("BEGIN", "SELECT")) for statement in statements)


def test_archive_http_is_private_csrf_guarded_and_excludes_other_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "alice@example.test", "Synthetic", now=2000000000)
        bob = store.login("bob", "bob@example.test", "Synthetic", now=2000000000)
        photo = PhotoService(store.engine).upload(
            alice.user, image_bytes(), "alice.jpg"
        )
        other = DocumentService(store.engine).upload(
            bob.user, synthetic_pdf(), "bob-private.pdf"
        )
        assert client.post("/api/export/archive", json={}).status_code == 401
        client.cookies.set("lifegather_session", alice.token)
        assert client.post("/api/export/archive", json={}).status_code == 403
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        response = client.post("/api/export/archive", json={}, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert re.fullmatch(
            r'attachment; filename="lifegather-archive-\d{8}T\d{6}Z\.zip"',
            response.headers["content-disposition"],
        )
        manifest, _, _ = unpack(response.content)
        assert [entry["id"] for entry in manifest["originals"]] == [photo["id"]]
        assert (
            other["id"].encode() not in response.content
            and b"bob-private" not in response.content
        )
        assert (
            client.post(
                "/api/export/archive", json={"user_id": bob.user.id}, headers=headers
            ).status_code
            == 422
        )
        with monkeypatch.context() as limits:
            limits.setattr(archives, "MAX_ARCHIVE_BYTES", 100)
            limited = client.post("/api/export/archive", json={}, headers=headers)
            assert limited.status_code == 413
            assert "content-disposition" not in limited.headers
        with store.engine.begin() as db:
            db.execute(
                text("UPDATE photos SET content_hash=:hash WHERE id=:id"),
                {"hash": "0" * 64, "id": photo["id"]},
            )
        invalid = client.post("/api/export/archive", json={}, headers=headers)
        assert invalid.status_code == 409
        assert "content-disposition" not in invalid.headers
