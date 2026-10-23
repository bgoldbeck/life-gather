from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from database_support import restore_copy
from fastapi.testclient import TestClient
from stored_files import files
from test_documents import synthetic_pdf
from test_mcp_http import rpc, signed_headers
from test_photos import image_bytes, reading
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.chat.service import SaveText, save_text
from lifegather.documents.service import DocumentService, DocumentText
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.library import LibraryPage, MemoryLibrary
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.photos.service import PhotoDelete, PhotoService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_library_current_search_history_and_source_categories(tmp_path: Path) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    library = MemoryLibrary(auth.engine)
    note = save_text(
        memory, actor, SaveText(text="Old filter 16x25", request_id="first")
    )
    correction = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=note.id, text="Current filter 20x30", request_id="correct"
        ),
    )["source"]
    assert library.list(actor, LibraryPage(query="Old filter"))["items"] == []
    old = library.list(actor, LibraryPage(query="Old filter", include_history=True))[
        "items"
    ]
    assert old[0]["id"] == note.id and not old[0]["is_current"]
    assert not old[0]["can_correct"]
    current = library.list(actor, LibraryPage(query="Current filter"))["items"]
    assert current[0]["id"] == correction["id"] and current[0]["is_correction"]
    assert current[0]["kind"] == "notes" and current[0]["can_correct"]
    assert library.list(bob, LibraryPage(include_history=True))["items"] == []
    assert (
        library.list(bob, LibraryPage(query="filter", include_history=True))["items"]
        == []
    )
    photo_service = PhotoService(auth.engine, files(auth.engine))
    photo = photo_service.upload(actor, image_bytes(), "synthetic-plate.jpg")
    photo_source = photo_service.save_reading(actor, photo["id"], reading())[
        "source_id"
    ]
    photo_correction = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=photo_source,
            text="Husqvarna 525L corrected transcription",
            request_id="photo-correct",
        ),
    )["source"]
    assert (
        library.list(actor, LibraryPage(kind="photos"))["items"][0]["id"]
        == photo_correction["id"]
    )
    latest = photo_service.get(actor, photo["id"])
    photo_service.delete(
        actor,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=latest["updated_at"]),
    )
    assert library.list(actor, LibraryPage(kind="photos"))["items"]
    documents = DocumentService(auth.engine, files(auth.engine))
    pdf = documents.upload(actor, synthetic_pdf(), "synthetic.pdf")
    reviewed = documents.save_text(
        actor,
        DocumentText(
            document_id=pdf["id"],
            text=pdf["extracted_text"],
            expected_updated_at=pdf["updated_at"],
        ),
    )
    corrected_pdf = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=reviewed["source_id"],
            text="Reviewed PDF correction",
            request_id="pdf-correct",
        ),
    )["source"]
    assert (
        library.list(actor, LibraryPage(kind="pdfs"))["items"][0]["id"]
        == corrected_pdf["id"]
    )
    unrelated = memory.ingest(actor, SourceInput(text="Other original evidence"))
    assert (
        library.list(actor, LibraryPage(kind="other"))["items"][0]["id"] == unrelated.id
    )
    assert {row["kind"] for row in library.list(actor, LibraryPage())["items"]} == {
        "notes",
        "photos",
        "pdfs",
        "other",
    }
    auth.engine.dispose()


def test_library_paging_ties_bounds_and_restore(tmp_path: Path) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    memory.clock = lambda: 100
    originals = [
        save_text(
            memory, actor, SaveText(text=f"Needle note {i}", request_id=f"note-{i}")
        )
        for i in range(28)
    ]
    other = save_text(memory, bob, SaveText(text="Needle private", request_id="bob"))
    library = MemoryLibrary(auth.engine)
    first = library.list(actor, LibraryPage(query="Needle"))
    second = library.list(
        actor, LibraryPage(query="Needle", cursor=first["next_cursor"])
    )
    assert len(first["items"]) == 25 and len(second["items"]) == 3
    assert second["next_cursor"] is None
    assert {i["id"] for i in first["items"] + second["items"]} == {
        s.id for s in originals
    }
    assert [i["id"] for i in first["items"]] == sorted(
        [s.id for s in originals], reverse=True
    )[:25]
    with pytest.raises(MemoryError):
        library.list(actor, LibraryPage(cursor=other.id))
    for query in ("!!!", "word " * 13):
        with pytest.raises(MemoryError):
            library.list(actor, LibraryPage(query=query))
    assert library.list(actor, LibraryPage(query='" OR private --'))["items"] == []
    snapshot = tmp_path / "library-snapshot.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    assert (
        MemoryLibrary(restored.engine).list(actor, LibraryPage(query="Needle")) == first
    )
    restored.engine.dispose()
    auth.engine.dispose()


def test_library_http_mcp_capture_concurrency_and_owner_isolation() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/memories").status_code == 401
        assert (
            client.post(
                "/api/memories", json={"text": "note", "request_id": "r"}
            ).status_code
            == 401
        )
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        body = {
            "text": "Literal <script>private café note</script>",
            "request_id": "capture",
        }
        assert (
            client.post(
                "/api/memories", headers={"Cookie": alice["Cookie"]}, json=body
            ).status_code
            == 403
        )
        with ThreadPoolExecutor(max_workers=3) as pool:
            saved = list(
                pool.map(
                    lambda _: client.post(
                        "/api/memories", headers=alice, json=body
                    ).json(),
                    range(3),
                )
            )
        assert saved[0] == saved[1] == saved[2]
        assert saved[0]["text"] == body["text"]
        assert (
            client.post(
                "/api/memories", headers=alice, json={**body, "text": "changed"}
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/api/memories?query=café&kind=notes&limit=1&include_history=false",
                headers=alice,
            ).json()["items"][0]["id"]
            == saved[0]["id"]
        )
        assert client.get("/api/memories", headers=bob).json()["items"] == []
        assert (
            client.get(
                "/api/memories?cursor=" + saved[0]["id"], headers=bob
            ).status_code
            == 400
        )
        assert client.get("/api/memories?limit=26", headers=alice).status_code == 422
        assert (
            client.get("/api/memories?kind=invalid", headers=alice).status_code == 422
        )
        assert (
            client.post(
                "/api/memories", headers=alice, json={**body, "user_id": "foreign"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/memories", headers=alice, content=b"x" * 32769
            ).status_code
            == 413
        )
        page = rpc(client, alice, "memory_library", {"query": "café"}).json()["result"]
        assert not page.get("isError"), page
        assert (
            rpc(client, bob, "memory_library", {}).json()["result"][
                "structuredContent"
            ]["items"]
            == []
        )
        assert app.state.private_settings.preferences(actor) is False
        # Capture stores source text only, never inferred graph entities.
        assert client.get("/api/graph/entities", headers=alice).json()["items"] == []
