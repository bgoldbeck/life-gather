import hashlib
import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from database_support import database
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stored_files import files as stored
from test_documents import synthetic_pdf
from test_maintenance import plan
from test_mcp_http import signed_headers
from test_recovery_bundle import installation

from lifegather.assets.type_schemas import TypeSave
from lifegather.assets.types import AssetTypes
from lifegather.auth.store import Account, AuthStore
from lifegather.chat.service import ChatService, TurnInput
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.export import COLLECTIONS
from lifegather.memory.models import Audit
from lifegather.memory.restore import (
    PersonalRestore,
    RestoreConflict,
    RestoreError,
    RestoreLimitError,
)
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryService
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoDelete, PhotoService


def png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 30), "navy").save(output, format="PNG")
    return output.getvalue()


def unpack(raw: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    with ZipFile(BytesIO(raw)) as package:
        content = {name: package.read(name) for name in package.namelist()}
    return (
        json.loads(content["manifest.json"]),
        json.loads(content["records.json"]),
        content,
    )


def pack(content: dict[str, bytes], compression: int = ZIP_STORED) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=compression) as package:
        for name, data in content.items():
            package.writestr(name, data)
    return output.getvalue()


def repack(
    raw: bytes,
    records: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> bytes:
    """Rewrite records/manifest consistently, as a careful tamperer would."""
    old_manifest, old_records, content = unpack(raw)
    manifest = manifest or old_manifest
    if records is not None:
        content["records.json"] = json.dumps(records).encode()
        manifest["records"]["size"] = len(content["records.json"])
        manifest["records"]["sha256"] = hashlib.sha256(
            content["records.json"]
        ).hexdigest()
    content["manifest.json"] = json.dumps(manifest).encode()
    return pack(content)


def target(tmp_path: Path, subject: str = "restored") -> tuple[AuthStore, Account]:
    store = AuthStore(database(tmp_path / "target"))
    store.migrate()
    return store, store.login(subject, subject + "@example.test", subject, now=1).user


def rich_archive(tmp_path: Path) -> tuple[Any, bytes]:
    case = installation(tmp_path)
    engine = case.store.engine
    DocumentService(engine, stored(engine)).upload(
        case.alice, synthetic_pdf(), "owner-document.pdf"
    )
    photos = PhotoService(engine, stored(engine))
    removed = photos.upload(case.alice, png(), "removed.png")
    photos.delete(
        case.alice,
        PhotoDelete(photo_id=removed["id"], expected_updated_at=removed["updated_at"]),
    )
    MaintenanceService(engine).create(case.alice, plan(case.primary))
    types = AssetTypes(engine)
    vehicle = types.list(case.alice)["items"][0]
    types.save(
        case.alice,
        TypeSave.model_validate(
            {
                "type_id": vehicle["id"],
                "expected_revision": vehicle["revision"],
                "request_id": "rename-vehicle",
                "name": "Family car",
                "fields": vehicle["fields"],
            }
        ),
    )
    chat = ChatService(engine)
    conversation = chat.create(case.alice)["id"]
    row, _ = chat.begin(
        case.alice,
        conversation,
        TurnInput(request_id="chat", mode="search", text="Synthetic question"),
    )
    chat.finish(case.alice, row["id"], {"text": "Synthetic answer", "sources": []})
    return case, PersonalArchive(engine, stored(engine)).download(case.alice)


def test_restore_round_trip_keeps_records_history_originals_and_search(
    tmp_path: Path,
) -> None:
    case, raw = rich_archive(tmp_path)
    _, records, content = unpack(raw)
    assert all(records["collections"][p.table.name] for p in COLLECTIONS[:6])
    store, actor = target(tmp_path)
    storage = stored(store.engine)
    result = PersonalRestore(store.engine, storage).restore(actor, raw)
    assert result["total_records"] == records["total_records"]
    assert result["originals"] == 2
    again = PersonalArchive(store.engine, storage).download(actor)
    _, restored, restored_content = unpack(again)
    audits = [
        row
        for row in restored["collections"]["memory_audit"]
        if row["operation"] == "personal_archive_restored"
    ]
    assert len(audits) == 1 and audits[0]["target_id"] == records["snapshot_at"]
    restored["collections"]["memory_audit"].remove(audits[0])
    assert restored["collections"] == records["collections"]
    originals = {k: v for k, v in content.items() if k.startswith("originals/")}
    assert {
        k: v for k, v in restored_content.items() if k.startswith("originals/")
    } == originals
    photo = next(
        row for row in records["collections"]["photos"] if row["deleted_at"] is None
    )
    raw_preview, mime = PhotoService(store.engine, storage).binary(actor, photo["id"])
    assert mime == "image/jpeg" and raw_preview.startswith(b"\xff\xd8")
    memory = MemoryService(store.engine)
    assert memory.search(actor, "mower")
    assert [fact.model_dump() for fact in memory.timeline(actor, case.primary)] == [
        {**fact} for fact in case.facts
    ]
    names = [item["name"] for item in AssetTypes(store.engine).list(actor)["items"]]
    assert names.count("Family car") == 1 and "Vehicle" not in names
    # The source account's other user and its own records are untouched.
    assert PersonalArchive(case.store.engine, stored(case.store.engine)).download(
        case.alice
    )


def test_restore_refuses_non_empty_account_and_repeat_without_changes(
    tmp_path: Path,
) -> None:
    _, raw = rich_archive(tmp_path)
    store, actor = target(tmp_path)
    MemoryService(store.engine).ingest(actor, SourceInput(text="Existing note"))
    with pytest.raises(RestoreConflict, match="already has saved records"):
        PersonalRestore(store.engine, stored(store.engine)).restore(actor, raw)
    other = store.login("second", "second@example.test", "Second", now=1).user
    PersonalRestore(store.engine, stored(store.engine)).restore(other, raw)
    with pytest.raises(RestoreConflict, match="already has saved records"):
        PersonalRestore(store.engine, stored(store.engine)).restore(other, raw)
    third = store.login("third", "third@example.test", "Third", now=1).user
    with pytest.raises(RestoreConflict, match="already exist in this installation"):
        PersonalRestore(store.engine, stored(store.engine)).restore(third, raw)
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).where(Audit.user_id == third.id)) == 0
    assert not list((tmp_path / "target" / "files" / "users" / third.id).glob("**/*"))


def test_restore_round_trip_keeps_non_pdf_documents(tmp_path: Path) -> None:
    # Exports omit the legacy page column for non-PDF documents; restore must
    # still accept the archive it produced (found by the browser checks).
    case = installation(tmp_path)
    engine = case.store.engine
    DocumentService(engine, stored(engine)).upload(
        case.alice, b"Synthetic receipt\nTotal 49.99 USD\n", "receipt.txt"
    )
    raw = PersonalArchive(engine, stored(engine)).download(case.alice)
    _, records, _ = unpack(raw)
    [document] = records["collections"]["documents"]
    assert document["format"] == "txt" and document["pages"] is None
    store, actor = target(tmp_path)
    storage = stored(store.engine)
    result = PersonalRestore(store.engine, storage).restore(actor, raw)
    assert result["total_records"] == records["total_records"]
    _, restored, _ = unpack(PersonalArchive(store.engine, storage).download(actor))
    assert restored["collections"]["documents"] == [document]


def test_restore_into_source_installation_is_refused(tmp_path: Path) -> None:
    case, raw = rich_archive(tmp_path)
    fresh = case.store.login("carol", "carol@example.test", "Carol", now=1).user
    with pytest.raises(RestoreConflict, match="already exist"):
        PersonalRestore(case.store.engine, stored(case.store.engine)).restore(
            fresh, raw
        )


def tampered(raw: bytes) -> list[tuple[str, bytes]]:
    manifest, records, content = unpack(raw)
    cases: list[tuple[str, bytes]] = []
    photo = next(e for e in manifest["originals"] if e["kind"] == "photos")

    changed = dict(content)
    changed["records.json"] = content["records.json"].replace(b"mower", b"MOWER")
    cases.append(("records hash", pack(changed)))

    changed = dict(content)
    changed[photo["path"]] = content[photo["path"]][:-1] + b"\x00"
    cases.append(("original hash", pack(changed)))

    changed = dict(content)
    del changed[photo["path"]]
    cases.append(("missing original", pack(changed)))

    changed = dict(content)
    changed["../escape.txt"] = b"x"
    cases.append(("extra member", pack(changed)))

    copy = json.loads(json.dumps(manifest))
    copy["originals"] = [e for e in copy["originals"] if e["id"] != photo["id"]]
    cases.append(("unlisted original", repack(raw, manifest=copy)))

    copy = json.loads(json.dumps(manifest))
    copy["format"] = "lifegather-personal-archive/2"
    cases.append(("archive format", repack(raw, manifest=copy)))

    changes: list[Callable[[dict[str, Any]], object]] = [
        lambda r: r.__setitem__("format", "lifegather-records/3"),
        lambda r: r["collections"]["memory_sources"][0].pop("text"),
        lambda r: r["collections"]["memory_sources"][0].__setitem__("user_id", "x"),
        lambda r: r["collections"]["memory_sources"][0].__setitem__("recorded_at", "1"),
        lambda r: r["collections"]["memory_facts"][0].__setitem__("subject_id", None),
        lambda r: r["collections"]["asset_types"][0].__setitem__("retired", 0),
        lambda r: r["collections"]["maintenance_revisions"][0].__setitem__(
            "due_on", "2026-13-01"
        ),
        lambda r: r["collections"].pop("photos"),
        lambda r: r.__setitem__("total_records", 1),
        lambda r: r["collections"]["memory_facts"][0].__setitem__(
            "subject_id", "00000000-0000-4000-8000-000000000000"
        ),
    ]
    for change in changes:
        copy = json.loads(json.dumps(records))
        change(copy)
        if "total_records" in copy and copy["total_records"] != 1:
            copy["counts"] = {k: len(v) for k, v in copy["collections"].items()}
        cases.append(("record change", repack(raw, records=copy)))
    cases.append(("not a zip", b"PK not really"))
    cases.append(("json", content["records.json"]))
    return cases


def test_restore_refuses_tampered_or_unsupported_archives_with_nothing_saved(
    tmp_path: Path,
) -> None:
    _, raw = rich_archive(tmp_path)
    store, actor = target(tmp_path)
    service = PersonalRestore(store.engine, stored(store.engine))
    for label, upload in tampered(raw):
        with pytest.raises(RestoreError):
            service.restore(actor, upload)
        with Session(store.engine) as db:
            assert db.scalar(select(func.count()).select_from(Photo)) == 0, label
            assert db.scalar(select(func.count()).where(Audit.user_id == actor.id)) == 0
    assert not list((tmp_path / "target" / "files").glob("**/*.*"))
    # A re-compressed but otherwise identical archive is still accepted.
    _, _, content = unpack(raw)
    assert service.restore(actor, pack(content, ZIP_DEFLATED))["originals"] == 2


def test_restore_limits_and_failed_storage_leave_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, raw = rich_archive(tmp_path)
    store, actor = target(tmp_path)
    storage = stored(store.engine)
    with pytest.raises(RestoreLimitError):
        PersonalRestore(store.engine, storage).restore(actor, raw + b"\0" * (64 << 20))
    calls: list[str] = []
    original_save = storage.save

    def failing(data: bytes, key: str) -> None:
        calls.append(key)
        if len(calls) == 3:
            from lifegather.storage.base import StorageError

            raise StorageError("disk full")
        original_save(data, key)

    monkeypatch.setattr(storage, "save", failing)
    with pytest.raises(RestoreError, match="Unable to store"):
        PersonalRestore(store.engine, storage).restore(actor, raw)
    assert all(not storage.exists(key) for key in calls)
    with Session(store.engine) as db:
        assert db.execute(text("SELECT count(*) FROM memory_sources")).scalar() == 0


def test_http_restore_requires_owner_csrf_and_maps_errors(tmp_path: Path) -> None:
    _, raw = rich_archive(tmp_path)
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "restore-owner")
        path = "/api/import/archive"
        zipped = {**headers, "Content-Type": "application/zip"}
        assert client.post(path, content=raw).status_code == 401
        assert (
            client.post(
                path,
                headers={
                    "Cookie": headers["Cookie"],
                    "Content-Type": "application/zip",
                },
                content=raw,
            ).status_code
            == 403
        )
        assert client.post(path, headers=headers, content=raw).status_code == 415
        assert client.post(path, headers=zipped, content=b"PK").status_code == 422
        assert (
            client.post(
                path, headers=zipped, content=b"x" * ((64 << 20) + 1)
            ).status_code
            == 413
        )
        result = client.post(path, headers=zipped, content=raw)
        assert result.status_code == 200, result.text
        assert result.json()["originals"] == 2
        repeat = client.post(path, headers=zipped, content=raw)
        assert repeat.status_code == 409
        assert "already has saved records" in repeat.json()["detail"]
