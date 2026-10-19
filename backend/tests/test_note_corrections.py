from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_mcp_http import rpc, signed_headers

from lifegather.auth.store import AuthStore
from lifegather.chat.service import ChatService, SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Episode, NoteRevision
from lifegather.memory.notes import CorrectionInput, NoteConflict, NoteService
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService


def setup(tmp_path: Path) -> tuple[Any, ...]:
    auth = AuthStore(tmp_path / "notes.sqlite3")
    auth.migrate()
    alice = auth.login("alice", "alice@example.test", "Alice", now=1).user
    bob = auth.login("bob", "bob@example.test", "Bob", now=1).user
    memory = MemoryService(auth.engine)
    original = save_text(
        memory, alice, SaveText(text="My filter is 16x25x1.", request_id="first")
    )
    return auth, alice, bob, memory, original, NoteService(auth.engine)


def correction(
    source_id: str, key: str = "correction-1", text: str = "My filter is 20x25x1."
) -> CorrectionInput:
    return CorrectionInput(source_id=source_id, request_id=key, text=text)


def test_correction_retains_original_recall_and_replay(tmp_path: Path) -> None:
    auth, alice, bob, memory, original, notes = setup(tmp_path)
    changed = notes.correct(alice, correction(original.id))
    current = changed["source"]["id"]
    assert memory.get_source(alice, original.id).text == original.text
    assert memory.get_source(alice, current).text == "My filter is 20x25x1."
    assert notes.correct(alice, correction(original.id)) == changed
    assert notes.describe(alice, original.id)["current_source_id"] == current
    assert notes.describe(alice, original.id)["is_current"] is False
    assert notes.describe(alice, current)["is_current"] is True
    assert memory.search(alice, "16x25x1") == []
    assert [s["id"] for s in ChatService(auth.engine).evidence(alice, "filter")] == [
        current
    ]
    assert memory.search(bob, "filter") == []
    with pytest.raises(MemoryError):
        notes.correct(bob, correction(original.id))
    with pytest.raises(MemoryError):
        notes.history(bob, current)
    with pytest.raises(NoteConflict):
        notes.correct(alice, correction(original.id, "stale", "My filter is 22x25x1."))
    with pytest.raises(NoteConflict):
        notes.correct(alice, correction(original.id, text="changed retry"))
    history = notes.history(alice, original.id)
    assert [s["id"] for s in history["items"]] == [original.id, current]
    assert len(memory.export_page(alice, "note_revisions")["items"]) == 1
    assert memory.export_page(bob, "note_revisions")["items"] == []


def test_many_revisions_search_paging_and_restore(tmp_path: Path) -> None:
    auth, alice, _, memory, original, notes = setup(tmp_path)
    source_id = original.id
    first_change = None
    for number in range(28):
        result = notes.correct(
            alice,
            correction(
                source_id, f"revision-{number}", f"My filter size revision {number}."
            ),
        )
        if first_change is None:
            first_change = result
        source_id = result["source"]["id"]
    assert len(memory.search(alice, "filter", 1)) == 1
    assert memory.search(alice, "filter", 1)[0]["id"] == source_id
    first = notes.history(alice, source_id)
    second = notes.history(alice, original.id, cursor=first["next_cursor"])
    assert len(first["items"]) == 25 and len(second["items"]) == 4
    assert len({s["id"] for s in first["items"] + second["items"]}) == 29
    # A retry returns the same saved correction, not a new branch in history.
    assert (
        notes.correct(
            alice, correction(original.id, "revision-0", "My filter size revision 0.")
        )
        == first_change
    )
    backup = tmp_path / "restored.sqlite3"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(backup)
    restored.migrate()
    assert NoteService(restored.engine).history(alice, source_id) == first
    assert (
        MemoryService(restored.engine).search(alice, "filter", 1)[0]["id"] == source_id
    )


def test_replay_clock_reversal_and_graph_evidence_unchanged(tmp_path: Path) -> None:
    auth, alice, bob, memory, original, _ = setup(tmp_path)
    notes = NoteService(auth.engine, clock=lambda: 0)
    item = memory.create_entity(
        alice,
        EntityInput(
            name="filter", kind="asset", source_id=original.id, operation_key="asset"
        ),
    )
    fact = memory.assert_fact(
        alice,
        FactInput(
            subject_id=item.id,
            predicate="size",
            value="16x25x1",
            source_id=original.id,
            quote=original.text,
            operation_key="size",
        ),
    )
    data = correction(original.id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: notes.correct(alice, data), range(4)))
    assert all(result == results[0] for result in results)
    revised = results[0]["source"]
    assert revised["recorded_at"] > original.recorded_at
    # Entity matches must cite the corrected source ID as well as its text.
    evidence = ChatService(auth.engine).evidence(alice, "filter")
    assert len(evidence) == 1 and evidence[0]["id"] == revised["id"]
    assert evidence[0]["text"] == revised["text"]
    reverted = notes.correct(alice, correction(revised["id"], "revert", original.text))
    assert reverted["source"]["id"] != original.id
    assert reverted["recorded_at"] > revised["recorded_at"]
    assert memory.facts(alice, item.id) == [fact]
    assert memory.get_entity(alice, item.id).source_id == original.id
    with pytest.raises(MemoryError):
        notes.correct(
            alice, correction(reverted["source"]["id"], "unchanged", original.text)
        )
    other = save_text(memory, bob, SaveText(text="Separate", request_id="bob"))
    for cursor in ("unknown", other.id):
        with pytest.raises(MemoryError):
            notes.history(alice, original.id, cursor)


@pytest.mark.usefixtures("legacy_audit_writer")
def test_upgrade_preserves_notes_sessions_settings_and_chat(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather
    from lifegather.chat.service import TurnInput
    from lifegather.credentials.service import PrivateSettings

    auth = AuthStore(tmp_path / "legacy.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with auth.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006_text_chat")
    signed = auth.login("legacy", "legacy@example.test", "Legacy", now=100)
    actor = signed.user
    memory = MemoryService(auth.engine)
    original = save_text(
        memory, actor, SaveText(text="Legacy filter note", request_id="legacy")
    )
    settings = PrivateSettings(auth.engine, None)
    settings.set_preferences(actor, True)
    chat = ChatService(auth.engine)
    conversation = chat.create(actor)["id"]
    turn, _ = chat.begin(
        actor,
        conversation,
        TurnInput(request_id="legacy-turn", mode="save", text=original.text),
    )
    chat.finish(actor, turn["id"], {"text": "Saved"})
    before = chat.turns(actor, conversation)
    auth.migrate()
    assert auth.authenticate(signed.token, now=101) is not None
    assert settings.preferences(actor) is True
    assert chat.turns(actor, conversation) == before
    assert memory.get_source(actor, original.id).text == original.text
    metadata = NoteService(auth.engine).describe(actor, original.id)
    assert metadata is not None and metadata["is_current"] is True
    changed = NoteService(auth.engine).correct(actor, correction(original.id))
    assert memory.search(actor, "filter")[0]["id"] == changed["source"]["id"]


def test_concurrent_edits_atomic_rollback_and_owner_constraints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth, alice, bob, memory, original, notes = setup(tmp_path)

    def edit(index: int) -> str:
        try:
            return str(
                notes.correct(
                    alice,
                    correction(original.id, f"edit-{index}", f"Filter edit {index}."),
                )["source"]["id"]
            )
        except NoteConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(edit, range(4)))
    assert results.count("conflict") == 3
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(NoteRevision)))) == 1
        assert len(list(db.scalars(select(Episode)))) == 2
    current = next(r for r in results if r != "conflict")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise MemoryError("Synthetic transaction failure")

    monkeypatch.setattr(notes, "_record", fail)
    with pytest.raises(MemoryError):
        notes.correct(alice, correction(current, "rollback", "Never committed filter."))
    assert memory.search(alice, "Never") == []
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(Episode)))) == 2
    bob_source = save_text(
        memory, bob, SaveText(text="Bob's separate note.", request_id="bob")
    )
    with pytest.raises(IntegrityError), auth.engine.begin() as connection:
        connection.execute(
            insert(NoteRevision).values(
                id="foreign-link",
                user_id=bob.id,
                root_source_id=original.id,
                previous_source_id=current,
                source_id=bob_source.id,
                request_id="attack",
                fingerprint="attack",
                recorded_at=1,
            )
        )


def test_http_mcp_authentication_history_and_immutable_sources() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, owner = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        source = save_text(
            MemoryService(app.state.auth_store.engine),
            owner,
            SaveText(text="My filter is 16x25x1.", request_id="original"),
        )
        path = f"/api/chat/sources/{source.id}/corrections"
        payload = {"request_id": "http-correction", "text": "My filter is 20x25x1."}
        assert client.post(path, json=payload).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": alice["Cookie"]}, json=payload
            ).status_code
            == 403
        )
        assert client.post(path, headers=bob, json=payload).status_code == 400
        changed = client.post(path, headers=alice, json=payload)
        assert changed.status_code == 200, changed.text
        current = changed.json()["source"]["id"]
        assert client.post(path, headers=alice, json=payload).json() == changed.json()
        assert (
            client.post(
                path, headers=alice, json={**payload, "request_id": "stale"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                path, headers=alice, json={**payload, "user_id": "foreign"}
            ).status_code
            == 422
        )
        assert (
            client.get(f"/api/chat/sources/{current}/history", headers=bob).status_code
            == 400
        )
        assert (
            client.get(
                f"/api/chat/sources/{current}/history?limit=26", headers=alice
            ).status_code
            == 422
        )
        viewed = client.get(f"/api/chat/sources/{source.id}", headers=alice).json()
        assert viewed["text"] == source.text and viewed["note"]["is_current"] is False
        read = rpc(client, alice, "memory_source", {"source_id": source.id}).json()[
            "result"
        ]["structuredContent"]
        assert read["note"]["current_source_id"] == current
        revised = rpc(
            client,
            alice,
            "memory_correct_note",
            {
                "source_id": current,
                "request_id": "mcp-correction",
                "text": "My filter is 22x25x1.",
            },
        ).json()["result"]["structuredContent"]
        assert revised["source"]["id"] != current
        history = rpc(
            client, alice, "memory_note_history", {"source_id": source.id}
        ).json()["result"]["structuredContent"]
        assert len(history["items"]) == 3
        unrelated = MemoryService(app.state.auth_store.engine).ingest(
            owner, SourceInput(text="An imported receipt.")
        )
        assert (
            client.post(
                f"/api/chat/sources/{unrelated.id}/corrections",
                headers=alice,
                json=payload,
            ).status_code
            == 400
        )
