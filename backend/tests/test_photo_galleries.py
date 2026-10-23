from io import BytesIO
from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_mcp_http import rpc, signed_headers
from test_personal_restore import repack, target, unpack

from lifegather.auth.store import Account, AuthStore
from lifegather.database import account_scope
from lifegather.main import create_app
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.export import GALLERIES
from lifegather.memory.models import Audit
from lifegather.memory.notes import NoteConflict
from lifegather.memory.restore import PersonalRestore
from lifegather.memory.service import MemoryError
from lifegather.photos.galleries import (
    GalleryAdd,
    GalleryCreate,
    GalleryDelete,
    GalleryList,
    GalleryRemove,
    GalleryService,
    GalleryUpdate,
)
from lifegather.photos.models import PhotoGallery, PhotoGalleryPhoto
from lifegather.photos.service import PhotoDelete, PhotoList, PhotoService

pytestmark = pytest.mark.usefixtures("configured_database")


def picture(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (60, 40), color).save(output, "JPEG")
    return output.getvalue()


def accounts(tmp_path: Path) -> tuple[AuthStore, Account, Account]:
    store = AuthStore(database(tmp_path / "data"))
    store.migrate()
    alice = store.login("alice", "a@example.test", "Alice", now=1).user
    bob = store.login("bob", "b@example.test", "Bob", now=1).user
    return store, alice, bob


def test_gallery_lifecycle_keeps_photos(tmp_path: Path) -> None:
    store, alice, _ = accounts(tmp_path)
    photos = PhotoService(store.engine, files(store.engine))
    galleries = GalleryService(store.engine)
    red, green, blue = (
        photos.upload(alice, picture(color), f"{color}.jpg")
        for color in ("red", "green", "blue")
    )
    moving = galleries.create(
        alice, GalleryCreate(title="  Moving   day ", event_on="2026-05-02")
    )
    assert moving["title"] == "Moving day" and moving["photo_count"] == 0
    # Repeating the same name and date returns the same gallery.
    assert (
        galleries.create(
            alice, GalleryCreate(title="moving day", event_on="2026-05-02")
        )["id"]
        == moving["id"]
    )
    with pytest.raises(NoteConflict):
        galleries.create(alice, GalleryCreate(title="Moving day"))
    undated = galleries.create(alice, GalleryCreate(title="Attic"))
    later = galleries.create(
        alice, GalleryCreate(title="Garden", event_on="2026-08-01")
    )
    assert [g["id"] for g in galleries.list(alice, GalleryList())["items"]] == [
        later["id"],
        moving["id"],
        undated["id"],
    ]

    added = galleries.add(
        alice,
        GalleryAdd(gallery_id=moving["id"], photo_ids=[green["id"], red["id"]]),
    )
    assert added["photo_count"] == 2 and added["added_count"] == 2
    assert added["cover_photo_id"] == green["id"]
    again = galleries.add(
        alice,
        GalleryAdd(gallery_id=moving["id"], photo_ids=[red["id"], blue["id"]]),
    )
    assert again["added_count"] == 1 and again["photo_count"] == 3
    listed = photos.list(alice, PhotoList(gallery_id=moving["id"]))["items"]
    assert {row["id"] for row in listed} == {red["id"], green["id"], blue["id"]}
    assert [
        g["id"] for g in galleries.list(alice, GalleryList(photo_id=red["id"]))["items"]
    ] == [moving["id"]]

    removed = galleries.remove(
        alice, GalleryRemove(gallery_id=moving["id"], photo_id=green["id"])
    )
    assert removed["photo_count"] == 2 and removed["cover_photo_id"] == red["id"]
    # Removing an absent photo is a safe replay.
    assert (
        galleries.remove(
            alice, GalleryRemove(gallery_id=moving["id"], photo_id=green["id"])
        )["updated_at"]
        == removed["updated_at"]
    )
    assert photos.get(alice, green["id"])["deleted_at"] is None

    with pytest.raises(NoteConflict):
        galleries.update(
            alice,
            GalleryUpdate(
                gallery_id=moving["id"],
                title="Move",
                expected_updated_at=moving["updated_at"],
            ),
        )
    with pytest.raises(NoteConflict):
        galleries.update(
            alice,
            GalleryUpdate(
                gallery_id=moving["id"],
                title="attic",
                expected_updated_at=removed["updated_at"],
            ),
        )
    renamed = galleries.update(
        alice,
        GalleryUpdate(
            gallery_id=moving["id"],
            title="House move",
            event_on=None,
            expected_updated_at=removed["updated_at"],
        ),
    )
    assert renamed["title"] == "House move" and renamed["event_on"] is None

    # Deleting a photo takes it out of every gallery.
    photos.delete(
        alice, PhotoDelete(photo_id=red["id"], expected_updated_at=red["updated_at"])
    )
    assert galleries.get(alice, moving["id"])["photo_count"] == 1
    with pytest.raises(MemoryError):
        galleries.add(alice, GalleryAdd(gallery_id=later["id"], photo_ids=[red["id"]]))

    with pytest.raises(NoteConflict):
        galleries.delete(
            alice, GalleryDelete(gallery_id=moving["id"], expected_updated_at=0)
        )
    deleted = GalleryDelete(
        gallery_id=moving["id"], expected_updated_at=renamed["updated_at"]
    )
    assert galleries.delete(alice, deleted)["deleted"]
    assert galleries.delete(alice, deleted)["deleted"]
    assert photos.get(alice, blue["id"])["deleted_at"] is None
    with Session(store.engine) as db:
        assert not db.scalars(
            select(PhotoGalleryPhoto).where(
                PhotoGalleryPhoto.gallery_id == moving["id"]
            )
        ).all()
        operations = set(db.scalars(select(Audit.operation)))
    assert {
        "photo_gallery_created",
        "photo_gallery_added",
        "photo_gallery_removed",
        "photo_gallery_updated",
        "photo_gallery_deleted",
    } <= operations


def test_gallery_input_is_validated() -> None:
    for bad in (
        {"title": " "},
        {"title": "x" * 81},
        {"title": "Trip", "event_on": "2026-13-01"},
        {"title": "Trip", "event_on": "May 2026"},
    ):
        with pytest.raises(ValidationError):
            GalleryCreate.model_validate(bad)
    with pytest.raises(ValidationError):
        GalleryAdd(gallery_id="g", photo_ids=["a", "a"])
    with pytest.raises(ValidationError):
        GalleryAdd(gallery_id="g", photo_ids=[str(n) for n in range(51)])


def test_galleries_are_private_to_one_account(tmp_path: Path) -> None:
    store, alice, bob = accounts(tmp_path)
    photos = PhotoService(store.engine, files(store.engine))
    galleries = GalleryService(store.engine)
    mine = photos.upload(alice, picture("red"), "red.jpg")
    theirs = photos.upload(bob, picture("blue"), "blue.jpg")
    gallery = galleries.create(alice, GalleryCreate(title="Trip"))
    galleries.add(alice, GalleryAdd(gallery_id=gallery["id"], photo_ids=[mine["id"]]))
    for attempt in (
        lambda: galleries.get(bob, gallery["id"]),
        lambda: galleries.add(
            bob, GalleryAdd(gallery_id=gallery["id"], photo_ids=[theirs["id"]])
        ),
        lambda: galleries.remove(
            bob, GalleryRemove(gallery_id=gallery["id"], photo_id=mine["id"])
        ),
        lambda: photos.list(bob, PhotoList(gallery_id=gallery["id"])),
        lambda: galleries.list(bob, GalleryList(photo_id=mine["id"])),
    ):
        with pytest.raises(MemoryError):
            attempt()
    # Alice cannot add Bob's photo to her own gallery either.
    with pytest.raises(MemoryError):
        galleries.add(
            alice, GalleryAdd(gallery_id=gallery["id"], photo_ids=[theirs["id"]])
        )
    assert galleries.list(bob, GalleryList())["items"] == []
    with account_scope(bob.id), Session(store.engine) as db:
        assert db.scalars(select(PhotoGallery)).all() == []
        assert db.scalars(select(PhotoGalleryPhoto)).all() == []


def test_gallery_http_and_mcp() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "gallery-owner")
        foreign, _ = signed_headers(app, "gallery-foreign")
        engine = app.state.auth_store.engine
        photo = PhotoService(engine, files(engine)).upload(
            actor, picture("green"), "green.jpg"
        )
        body = {"title": "Kitchen remodel", "event_on": "2026-03-14"}
        assert client.post("/api/photo-galleries", json=body).status_code == 401
        assert (
            client.post(
                "/api/photo-galleries", headers={"Cookie": headers["Cookie"]}, json=body
            ).status_code
            == 403
        )
        created = client.post("/api/photo-galleries", headers=headers, json=body)
        assert created.status_code == 201
        gallery = created.json()
        path = f"/api/photo-galleries/{gallery['id']}"
        added = client.post(
            path + "/photos", headers=headers, json={"photo_ids": [photo["id"]]}
        ).json()
        assert added["photo_count"] == 1
        assert (
            client.post(
                path + "/photos", headers=foreign, json={"photo_ids": [photo["id"]]}
            ).status_code
            == 400
        )
        assert client.get(path, headers=foreign).status_code == 400
        page = client.get(
            "/api/photos", params={"gallery_id": gallery["id"]}, headers=headers
        ).json()
        assert [row["id"] for row in page["items"]] == [photo["id"]]
        held = client.get(f"/api/photos/{photo['id']}/galleries", headers=headers)
        assert [row["id"] for row in held.json()["items"]] == [gallery["id"]]
        listing = rpc(client, headers, "photo_gallery_list", {}).json()["result"]
        assert listing["structuredContent"]["items"][0]["title"] == "Kitchen remodel"
        assert (
            rpc(client, foreign, "photo_gallery_list", {}).json()["result"][
                "structuredContent"
            ]["items"]
            == []
        )
        assert rpc(client, foreign, "photo_list", {"gallery_id": gallery["id"]}).json()[
            "result"
        ]["isError"]
        edited = client.post(
            path + "/update",
            headers=headers,
            json={
                "title": "Kitchen",
                "event_on": None,
                "expected_updated_at": added["updated_at"],
            },
        )
        assert edited.status_code == 200 and edited.json()["title"] == "Kitchen"
        stale = client.post(
            path + "/delete", headers=headers, json={"expected_updated_at": 0}
        )
        assert stale.status_code == 409
        assert (
            client.post(
                path + "/photos/remove", headers=headers, json={"photo_id": photo["id"]}
            ).json()["photo_count"]
            == 0
        )
        current = client.get(path, headers=headers).json()
        assert client.post(
            path + "/delete",
            headers=headers,
            json={"expected_updated_at": current["updated_at"]},
        ).json() == {"id": gallery["id"], "deleted": True}
        assert client.get("/api/photo-galleries", headers=headers).json() == {
            "items": []
        }


def test_archive_keeps_galleries_and_older_archives_restore(tmp_path: Path) -> None:
    store, alice, _ = accounts(tmp_path)
    photos = PhotoService(store.engine, files(store.engine))
    galleries = GalleryService(store.engine)
    photo = photos.upload(alice, picture("red"), "red.jpg")
    gallery = galleries.create(
        alice, GalleryCreate(title="Holiday", event_on="2026-12-24")
    )
    galleries.add(alice, GalleryAdd(gallery_id=gallery["id"], photo_ids=[photo["id"]]))
    raw = PersonalArchive(store.engine, files(store.engine)).download(alice)
    manifest, records, _ = unpack(raw)
    assert records["counts"]["photo_galleries"] == 1
    assert records["counts"]["photo_gallery_photos"] == 1
    assert "user_id" not in records["collections"]["photo_galleries"][0]

    restored, actor = target(tmp_path / "restored")
    PersonalRestore(restored.engine, files(restored.engine)).restore(actor, raw)
    again = GalleryService(restored.engine).list(actor, GalleryList())["items"]
    assert [(g["id"], g["title"], g["event_on"], g["photo_count"]) for g in again] == [
        (gallery["id"], "Holiday", "2026-12-24", 1)
    ]

    older = dict(records, format="lifegather-records/6")
    for key in ("collections", "counts"):
        older[key] = {k: v for k, v in records[key].items() if k not in GALLERIES}
    older["total_records"] -= 2
    old, actor = target(tmp_path / "old")
    PersonalRestore(old.engine, files(old.engine)).restore(
        actor, repack(raw, older, dict(manifest, records_format="lifegather-records/6"))
    )
    assert GalleryService(old.engine).list(actor, GalleryList())["items"] == []
    assert len(PhotoService(old.engine).list(actor, PhotoList())["items"]) == 1
