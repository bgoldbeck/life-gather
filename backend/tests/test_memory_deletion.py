from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_mcp_http import signed_headers
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.deletion import MemoryDelete, MemoryDeleteMany, MemoryDeletion
from lifegather.memory.library import LibraryPage, MemoryLibrary
from lifegather.memory.models import Audit, Evidence
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.restore import PersonalRestore
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import DELETED_TEXT, MemoryError
from lifegather.search.service import SearchQuery, SearchService

pytestmark = pytest.mark.usefixtures("configured_database")


def many(*ids: str) -> MemoryDeleteMany:
    return MemoryDeleteMany(memories=[MemoryDelete(source_id=i) for i in ids])


def receipts(store: AuthStore) -> list[str]:
    with Session(store.engine) as db:
        return list(
            db.scalars(
                select(Audit.target_id).where(Audit.operation == "source_deleted")
            )
        )


def test_delete_removes_text_from_list_search_and_quotes_but_keeps_facts(
    tmp_path: Path,
) -> None:
    store, alice, bob, memory, _ = setup(tmp_path)
    library = MemoryLibrary(store.engine)
    note = save_text(
        memory, alice, SaveText(text="Synthetic blue kayak paddle", request_id="n1")
    )
    kept = save_text(
        memory, alice, SaveText(text="Synthetic kayak trailer", request_id="n2")
    )
    kayak = memory.create_entity(
        alice,
        EntityInput(
            name="Kayak", kind="asset", source_id=note.id, operation_key="kayak"
        ),
    )
    fact = memory.assert_fact(
        alice,
        FactInput(
            subject_id=kayak.id,
            predicate="color",
            value="blue",
            status="stated",
            source_id=note.id,
            quote="blue kayak",
            operation_key="kayak-color",
        ),
    )
    deletion = MemoryDeletion(store.engine)
    with pytest.raises(MemoryError):
        deletion.delete_many(bob, many(note.id))
    result = deletion.delete_many(alice, many(note.id))
    assert result["deleted_count"] == 1 and result["versions_deleted"] == 1
    ids = [item["id"] for item in library.list(alice, LibraryPage())["items"]]
    assert ids == [kept.id]
    assert library.list(alice, LibraryPage(query="paddle"))["items"] == []
    assert [item["id"] for item in memory.search(alice, "kayak")] != []
    assert note.id not in [item["id"] for item in memory.search(alice, "kayak")]
    assert memory.get_source(alice, note.id).text == DELETED_TEXT
    assert memory.source_deleted(alice, note.id)
    assert not memory.source_deleted(alice, kept.id)
    # The fact and its evidence link remain; only the quoted text is cleared.
    assert [f.id for f in memory.facts(alice, kayak.id)] == [fact.id]
    with Session(store.engine) as db:
        quotes = list(db.scalars(select(Evidence.quote)))
    assert quotes == [None]
    # Repeating is idempotent: no second receipt.
    assert deletion.delete_many(alice, many(note.id))["versions_deleted"] == 0
    assert receipts(store) == [note.id]


def test_delete_note_removes_every_version_and_blocks_correction(
    tmp_path: Path,
) -> None:
    store, alice, _, memory, _ = setup(tmp_path)
    notes = NoteService(store.engine)
    original = save_text(
        memory, alice, SaveText(text="Synthetic filter 16x25", request_id="o")
    )
    corrected = notes.correct(
        alice,
        CorrectionInput(source_id=original.id, text="Filter 20x30", request_id="c"),
    )["source"]
    result = MemoryDeletion(store.engine).delete_many(alice, many(corrected["id"]))
    assert result["versions_deleted"] == 2
    assert sorted(receipts(store)) == sorted([original.id, corrected["id"]])
    library = MemoryLibrary(store.engine)
    assert library.list(alice, LibraryPage(include_history=True))["items"] == []
    assert notes.describe(alice, corrected["id"]) is None
    with pytest.raises(MemoryError):
        notes.correct(
            alice,
            CorrectionInput(source_id=corrected["id"], text="New", request_id="d"),
        )
    # Re-ingesting the same identified source does not revive its text.
    again = save_text(
        memory, alice, SaveText(text="Synthetic filter 16x25", request_id="o")
    )
    assert again.id == original.id and again.text == DELETED_TEXT
    assert library.list(alice, LibraryPage(query="filter"))["items"] == []
    # A new note with the same words is a new memory.
    fresh = save_text(
        memory, alice, SaveText(text="Synthetic filter 16x25", request_id="new")
    )
    assert [
        i["id"] for i in library.list(alice, LibraryPage(query="filter"))["items"]
    ] == [fresh.id]


def test_delete_many_is_all_or_nothing_and_bounded(tmp_path: Path) -> None:
    store, alice, _, memory, _ = setup(tmp_path)
    first = memory.ingest(
        alice,
        SourceInput(
            text="Synthetic email receipt",
            source_type="email",
            namespace="gmail-memory:test",
            external_id="m1",
        ),
    )
    deletion = MemoryDeletion(store.engine)
    with pytest.raises(MemoryError):
        deletion.delete_many(alice, many(first.id, "missing"))
    assert not memory.source_deleted(alice, first.id)
    with pytest.raises(MemoryError):
        deletion.delete_many(alice, many(first.id, first.id))
    with pytest.raises(ValidationError):
        many(*[str(i) for i in range(26)])
    with pytest.raises(ValidationError):
        MemoryDeleteMany(memories=[])
    deletion.delete_many(alice, many(first.id))
    # A re-scan of the same email keeps the tombstone out of search.
    memory.ingest(
        alice,
        SourceInput(
            text="Synthetic email receipt",
            source_type="email",
            namespace="gmail-memory:test",
            external_id="m1",
        ),
    )
    assert memory.get_source(alice, first.id).text == DELETED_TEXT
    with pytest.raises(MemoryError):
        memory.search(alice, "")
    assert not memory.search(alice, "receipt")


def test_deleted_memory_stays_deleted_after_archive_restore(tmp_path: Path) -> None:
    store, alice, _, memory, _ = setup(tmp_path / "source")
    note = save_text(
        memory, alice, SaveText(text="Synthetic garage shelf", request_id="g")
    )
    MemoryDeletion(store.engine).delete_many(alice, many(note.id))
    raw = PersonalArchive(store.engine, files(store.engine)).download(alice)
    target = AuthStore(database(tmp_path / "target"))
    target.migrate()
    actor = target.login("r", "r@example.test", "R", now=1).user
    PersonalRestore(target.engine, files(target.engine)).restore(actor, raw)
    restored = MemoryLibrary(target.engine)
    assert restored.list(actor, LibraryPage(include_history=True))["items"] == []
    from lifegather.memory.service import MemoryService

    assert not MemoryService(target.engine).search(actor, "deleted")
    assert not MemoryService(target.engine).search(actor, "garage")
    assert (
        SearchService(target.engine).find(actor, SearchQuery(q="deleted memory"))[
            "items"
        ]
        == []
    )


def test_delete_http_requires_write_session_and_reports_deleted() -> None:
    app = create_app()
    with TestClient(app) as client:
        body = {"memories": [{"source_id": "x"}]}
        assert client.post("/api/memories/delete-many", json=body).status_code == 401
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        saved = client.post(
            "/api/memories",
            headers=alice,
            json={"text": "Synthetic ladder note", "request_id": "ladder"},
        ).json()
        body = {"memories": [{"source_id": saved["id"]}]}
        assert (
            client.post(
                "/api/memories/delete-many",
                headers={"Cookie": alice["Cookie"]},
                json=body,
            ).status_code
            == 403
        )
        assert (
            client.post("/api/memories/delete-many", headers=bob, json=body).status_code
            == 400
        )
        assert (
            client.post(
                "/api/memories/delete-many",
                headers=alice,
                json={"memories": [{"source_id": saved["id"], "user_id": "x"}]},
            ).status_code
            == 422
        )
        response = client.post("/api/memories/delete-many", headers=alice, json=body)
        assert response.status_code == 200 and response.json()["deleted_count"] == 1
        assert client.get("/api/memories", headers=alice).json()["items"] == []
        source = client.get("/api/chat/sources/" + saved["id"], headers=alice).json()
        assert source["deleted"] is True and source["note"] is None
        assert source["text"] == DELETED_TEXT
