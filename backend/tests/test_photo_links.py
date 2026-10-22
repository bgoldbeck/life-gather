from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import restore_copy
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stored_files import files
from test_mcp_http import rpc, signed_headers
from test_photos import image_bytes
from test_unit_corrections import prepared

from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Audit
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.models import Photo, PhotoAsset
from lifegather.photos.service import (
    PhotoAttach,
    PhotoDelete,
    PhotoDetach,
    PhotoList,
    PhotoService,
)


def test_existing_photo_link_preserves_bytes_evidence_units_and_safe_replay(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, _, line, target, _ = prepared(tmp_path)
    service = PhotoService(auth.engine, files(auth.engine))
    row = service.upload(
        actor, image_bytes(), "synthetic.jpg", "receipt", line["asset_ids"][0]
    )
    facts = memory.export_page(actor, "facts")
    entities = memory.export_page(actor, "entities")
    request = PhotoAttach(
        photo_id=row["id"], asset_id=target.id, expected_updated_at=row["updated_at"]
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        linked = list(pool.map(lambda _: service.link(actor, request), range(2)))
    assert linked[0] == linked[1]
    assert linked[0]["updated_at"] > row["updated_at"]
    assert service.binary(actor, row["id"], True)[0] == image_bytes()
    for asset_id in (line["asset_ids"][0], target.id):
        assert (
            service.list(actor, PhotoList(asset_id=asset_id))["items"][0]["id"]
            == row["id"]
        )
    assert reconcile.get(actor, line["id"]).asset_ids == line["asset_ids"]
    assert memory.export_page(actor, "facts") == facts
    assert memory.export_page(actor, "entities") == entities
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count()).select_from(Photo)) == 1
        assert db.scalar(select(func.count()).select_from(PhotoAsset)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.operation == "photo_attached")
            )
            == 2
        )
    snapshot = tmp_path / "linked.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    assert (
        PhotoService(restored.engine, files(restored.engine)).link(actor, request)
        == linked[0]
    )
    assert (
        PhotoService(restored.engine, files(restored.engine)).binary(
            actor, row["id"], True
        )[0]
        == image_bytes()
    )


def test_stale_attach_cannot_restore_a_later_removed_link_or_deleted_photo(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _, _, line, target, _ = prepared(tmp_path)
    service = PhotoService(auth.engine, files(auth.engine))
    row = service.upload(
        actor, image_bytes(), "synthetic.jpg", asset_id=line["asset_ids"][0]
    )
    request = PhotoAttach(
        photo_id=row["id"], asset_id=target.id, expected_updated_at=row["updated_at"]
    )
    with pytest.raises(MemoryError):
        service.link(bob, request)
    foreign_source = memory.ingest(bob, SourceInput(text="Private synthetic target"))
    foreign = memory.create_entity(
        bob,
        EntityInput(
            name="Foreign item",
            kind="asset",
            source_id=foreign_source.id,
            operation_key="foreign",
        ),
    )
    with pytest.raises(MemoryError):
        service.link(actor, request.model_copy(update={"asset_id": foreign.id}))
    with pytest.raises(NoteConflict):
        service.link(actor, request.model_copy(update={"expected_updated_at": 0}))
    linked = service.link(actor, request)
    removed = service.detach(
        actor,
        PhotoDetach(
            photo_id=row["id"],
            asset_id=target.id,
            expected_updated_at=linked["updated_at"],
        ),
    )
    with pytest.raises(NoteConflict):
        service.link(actor, request)
    assert not service.list(actor, PhotoList(asset_id=target.id))["items"]
    assert service.list(actor, PhotoList(asset_id=line["asset_ids"][0]))["items"]
    service.delete(
        actor,
        PhotoDelete(photo_id=row["id"], expected_updated_at=removed["updated_at"]),
    )
    with pytest.raises(MemoryError, match="deleted"):
        service.link(actor, request)


def test_failed_attachment_rolls_back_the_link_and_photo_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, _, _, _, _, _, target, _ = prepared(tmp_path)
    service = PhotoService(auth.engine, files(auth.engine))
    row = service.upload(actor, image_bytes(), "synthetic.jpg")

    def fail(*args: Any) -> None:
        raise MemoryError("Synthetic attachment failure")

    monkeypatch.setattr(service.memory, "_audit", fail)
    with pytest.raises(MemoryError, match="Synthetic"):
        service.link(
            actor,
            PhotoAttach(
                photo_id=row["id"],
                asset_id=target.id,
                expected_updated_at=row["updated_at"],
            ),
        )
    assert service.get(actor, row["id"]) == row
    assert not service.list(actor, PhotoList(asset_id=target.id))["items"]


def test_existing_photo_http_mcp_auth_csrf_and_request_limit() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "photo-link-owner")
        foreign, _ = signed_headers(app, "photo-link-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        source = memory.ingest(actor, SourceInput(text="Synthetic item"))
        target = memory.create_entity(
            actor,
            EntityInput(
                name="Target", kind="asset", source_id=source.id, operation_key="target"
            ),
        )
        row = PhotoService(engine, files(engine)).upload(
            actor, image_bytes(), "synthetic.jpg"
        )
        body = {
            "photo_id": row["id"],
            "asset_id": target.id,
            "expected_updated_at": row["updated_at"],
        }
        path = "/api/photos/attach"
        assert client.post(path, json=body).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": headers["Cookie"]}, json=body
            ).status_code
            == 403
        )
        assert client.post(path, headers=foreign, json=body).status_code == 400
        assert rpc(client, foreign, "photo_attach", body).json()["result"]["isError"]
        result = rpc(client, headers, "photo_attach", body).json()["result"][
            "structuredContent"
        ]
        assert client.post(path, headers=headers, json=body).json() == result
        assert client.post(path, content=b" " * 32769).status_code == 413
