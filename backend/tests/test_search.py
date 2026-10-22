from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from stored_files import files
from test_asset_consolidation import prepared
from test_documents import synthetic_pdf
from test_mcp_http import signed_headers
from test_photos import image_bytes, reading

from lifegather.chat.service import SaveText, save_text
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoAttach, PhotoDelete, PhotoService
from lifegather.search.service import SearchQuery, SearchService


def kinds(result: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item["kind"], item["title"]) for item in result["items"]]


def test_search_spans_records_photos_documents_and_sources(tmp_path: Path) -> None:
    auth, actor, bob, memory, source, records, consolidation, request = prepared(
        tmp_path
    )
    search = SearchService(auth.engine)
    memory.create_entity(
        actor,
        EntityInput(
            name="Mower shed", kind="place", source_id=source.id, operation_key="shed"
        ),
    )
    result = search.find(actor, SearchQuery(q="MOWER"))
    titles = kinds(result)
    assert ("asset", "first mower") in titles
    assert ("asset", "second mower") in titles
    assert ("record", "Mower shed") in titles
    source_hit = next(i for i in result["items"] if i["kind"] == "source")
    assert source_hit["id"] == source.id and source_hit["photo_id"] is None
    # All words must match, in any order, anywhere in the field.
    assert kinds(search.find(actor, SearchQuery(q="mower second"))) == [
        ("asset", "second mower"),
        ("source", "Synthetic first and second mower. Red. Blue."),
    ]
    assert search.find(bob, SearchQuery(q="mower"))["items"] == []

    # A merged duplicate appears once, under the surviving record.
    consolidation.apply(actor, request())
    merged = [
        item["title"]
        for item in search.find(actor, SearchQuery(q="mower"))["items"]
        if item["kind"] == "asset"
    ]
    assert merged == ["first mower"]

    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "garage nameplate.jpg")
    reading_source = photos.save_reading(actor, photo["id"], reading())["source_id"]
    found = search.find(actor, SearchQuery(q="nameplate"))["items"]
    assert [(i["kind"], i["id"]) for i in found] == [("photo", photo["id"])]
    transcribed = next(
        i
        for i in search.find(actor, SearchQuery(q="husqvarna 525L"))["items"]
        if i["id"] == reading_source
    )
    assert transcribed["photo_id"] == photo["id"]

    documents = DocumentService(auth.engine, files(auth.engine))
    pdf = documents.upload(actor, synthetic_pdf(), "warranty card.pdf")
    by_name = search.find(actor, SearchQuery(q="warranty"))["items"]
    assert [(i["kind"], i["id"]) for i in by_name] == [("document", pdf["id"])]
    words = pdf["extracted_text"].split()[:2]
    by_text = search.find(actor, SearchQuery(q=" ".join(words)))["items"]
    assert ("document", pdf["id"]) in [(i["kind"], i["id"]) for i in by_text]

    latest = photos.get(actor, photo["id"])
    photos.delete(
        actor,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=latest["updated_at"]),
    )
    assert search.find(actor, SearchQuery(q="nameplate"))["items"] == []
    auth.engine.dispose()


def test_search_hides_superseded_notes_and_treats_wildcards_literally(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, *_ = prepared(tmp_path)
    search = SearchService(auth.engine)
    note = save_text(memory, actor, SaveText(text="Filter 16x25 100%", request_id="n"))
    corrected = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(source_id=note.id, text="Filter 20x30", request_id="c"),
    )["source"]
    hits = [i["id"] for i in search.find(actor, SearchQuery(q="filter"))["items"]]
    assert corrected["id"] in hits and note.id not in hits
    memory.ingest(actor, SourceInput(text="Discount 50% off", external_id="pct"))
    memory.ingest(actor, SourceInput(text="Discount 50 dollars", external_id="usd"))
    literal = search.find(actor, SearchQuery(q="50%"))["items"]
    assert [i["title"] for i in literal] == ["Discount 50% off"]
    underscore = search.find(actor, SearchQuery(q="_"))["items"]
    assert underscore == []
    auth.engine.dispose()


def test_search_bounds_and_limits(tmp_path: Path) -> None:
    auth, actor, _, memory, source, *_ = prepared(tmp_path)
    search = SearchService(auth.engine)
    for index in range(4):
        memory.create_entity(
            actor,
            EntityInput(
                name=f"spare mower {index}",
                kind="asset",
                source_id=source.id,
                operation_key=f"spare-{index}",
            ),
        )
    limited = search.find(actor, SearchQuery(q="spare", limit=2))["items"]
    assert [i["title"] for i in limited] == ["spare mower 0", "spare mower 1"]
    with pytest.raises(MemoryError):
        search.find(actor, SearchQuery(q="   "))
    with pytest.raises(MemoryError):
        search.find(actor, SearchQuery(q="a b c d e f g h i"))
    with pytest.raises(ValidationError):
        SearchQuery(q="x" * 201)
    auth.engine.dispose()


def test_photo_lists_its_assets_once_after_merge(tmp_path: Path) -> None:
    auth, actor, bob, _, _, records, consolidation, request = prepared(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "plate.jpg", "photo", records[1].id)
    assert photos.assets(actor, photo["id"]) == (
        {"id": records[1].id, "name": "second mower"},
    )
    latest = photos.get(actor, photo["id"])
    photos.link(
        actor,
        PhotoAttach(
            photo_id=photo["id"],
            asset_id=records[0].id,
            expected_updated_at=latest["updated_at"],
        ),
    )
    assert len(photos.assets(actor, photo["id"])) == 2
    consolidation.apply(actor, request())
    assert photos.assets(actor, photo["id"]) == (
        {"id": records[0].id, "name": "first mower"},
    )
    with pytest.raises(MemoryError):
        photos.assets(bob, photo["id"])
    auth.engine.dispose()


def test_search_and_photo_assets_http() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/search?q=mower").status_code == 401
        alice, actor = signed_headers(app, "search-alice")
        bob, _ = signed_headers(app, "search-bob")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        source = memory.ingest(actor, SourceInput(text="Synthetic blue kayak"))
        kayak = memory.create_entity(
            actor,
            EntityInput(
                name="blue kayak", kind="asset", source_id=source.id, operation_key="k"
            ),
        )
        response = client.get("/api/search?q=kayak", headers=alice)
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "kayak"
        assert ("asset", kayak.id) in [(i["kind"], i["id"]) for i in body["items"]]
        assert client.get("/api/search?q=kayak", headers=bob).json()["items"] == []
        assert client.get("/api/search?q=", headers=alice).status_code == 422
        assert (
            client.get("/api/search?q=kayak&limit=11", headers=alice).status_code == 422
        )

        upload = client.post(
            f"/api/photos?asset_id={kayak.id}",
            headers={**alice, "X-File-Name": "kayak.jpg", "Content-Type": "image/jpeg"},
            content=image_bytes(),
        )
        assert upload.status_code == 201
        photo_id = upload.json()["id"]
        linked = client.get(f"/api/photos/{photo_id}/assets", headers=alice)
        assert linked.json() == {"items": [{"id": kayak.id, "name": "blue kayak"}]}
        assert client.get(
            f"/api/photos/{photo_id}/assets", headers=bob
        ).status_code in {
            400,
            404,
        }
