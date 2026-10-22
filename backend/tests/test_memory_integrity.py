from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from database_support import database, restore_copy
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lifegather.auth.store import Account, AuthStore
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Assertion, Episode
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService


def setup(tmp_path: Path) -> tuple[AuthStore, MemoryService, Account, Account]:
    auth = AuthStore(database(tmp_path / "memory"))
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "A", now=1).user
    bob = auth.login("bob", "b@example.test", "B", now=1).user
    return auth, MemoryService(auth.engine), alice, bob


def item(memory: MemoryService, actor: Account, label: str) -> tuple[str, str]:
    source = memory.ingest(actor, SourceInput(text="I own " + label))
    entity = memory.create_entity(
        actor,
        EntityInput(
            name=label,
            kind="asset",
            source_id=source.id,
            operation_key=label,
        ),
    )
    return entity.id, source.id


def test_relations_and_database_owner_constraints(tmp_path: Path) -> None:
    auth, memory, alice, bob = setup(tmp_path)
    trimmer, source = item(memory, alice, "trimmer")
    retailer, _ = item(memory, alice, "retailer")
    foreign, foreign_source = item(memory, bob, "private tool")
    relation = FactInput(
        subject_id=trimmer,
        predicate="bought_from",
        object_id=retailer,
        source_id=source,
        operation_key="relation",
    )
    fact = memory.assert_fact(alice, relation)
    assert memory.assert_fact(alice, relation).id == fact.id
    graph = memory.related(alice, trimmer, depth=2)
    assert {node.id for node in graph["nodes"]} == {trimmer, retailer}
    assert graph["edges"][0].object_id == retailer
    with pytest.raises(MemoryError):
        memory.assert_fact(
            alice,
            relation.model_copy(
                update={"object_id": foreign, "operation_key": "attack"}
            ),
        )
    with pytest.raises(MemoryError):
        memory.attach_evidence(bob, fact.id, foreign_source)
    with pytest.raises(MemoryError):
        memory.correct_fact(bob, fact.id, relation)
    with pytest.raises(MemoryError):
        memory.attach_evidence(alice, fact.id, foreign_source)
    # The database itself rejects a cross-user source link, even without services.
    with pytest.raises(IntegrityError), auth.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO memory_entities "
                "(id,user_id,name,normalized_name,kind,source_id,"
                "operation_key,fingerprint,recorded_at) "
                "VALUES (:id,:owner,'bad','bad','asset',:source,'bad','bad',1)"
            ),
            {"id": str(uuid4()), "owner": alice.id, "source": foreign_source},
        )
    assert memory.export_page(bob, "facts")["items"] == []
    assert memory.export_page(bob, "evidence")["items"] == []
    assert len(memory.list_entities(alice)["items"]) == 2


def test_unknown_time_quotes_and_atomic_failed_corrections(tmp_path: Path) -> None:
    auth, memory, alice, _ = setup(tmp_path)
    entity, source = item(memory, alice, "trimmer")
    value = FactInput(
        subject_id=entity,
        predicate="price",
        value=None,
        status="unknown",
        source_id=source,
        operation_key="price-unknown",
    )
    fact = memory.assert_fact(alice, value)
    assert memory.facts(alice, entity)[0].value is None
    assert memory.facts(alice, entity)[0].valid_from is None
    assert memory.facts(alice, entity, world_date="2024-01-01") == []
    with pytest.raises(MemoryError, match="quote"):
        memory.correct_fact(
            alice,
            fact.id,
            value.model_copy(
                update={
                    "operation_key": "bad-correction",
                    "quote": "invented evidence",
                }
            ),
        )
    assert memory.facts(alice, entity)[0].id == fact.id
    with pytest.raises(MemoryError, match="conflict"):
        memory.assert_fact(alice, value.model_copy(update={"value": 349}))
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(Assertion)))) == 1
    with pytest.raises(ValidationError):
        FactInput(
            subject_id=entity,
            predicate="owned",
            source_id=source,
            operation_key="missing",
        )
    with pytest.raises(ValidationError):
        FactInput(
            subject_id=entity,
            predicate="owned",
            value=True,
            object_id=entity,
            source_id=source,
            operation_key="both",
        )
    with pytest.raises(ValidationError):
        FactInput(
            subject_id=entity,
            predicate="owned",
            value=True,
            source_id=source,
            valid_from=date(2025, 1, 1),
            valid_to=date(2024, 1, 1),
            operation_key="dates",
        )


def test_evidence_arrival_time_and_correction_provenance(tmp_path: Path) -> None:
    auth, _, alice, _ = setup(tmp_path)
    tick = [100]
    memory = MemoryService(auth.engine, clock=lambda: tick[0])
    entity, source = item(memory, alice, "trimmer")
    fact = memory.assert_fact(
        alice,
        FactInput(
            subject_id=entity,
            predicate="owned",
            value=True,
            source_id=source,
            operation_key="owned",
        ),
    )
    tick[0] = 200
    receipt = memory.ingest(alice, SourceInput(text="Receipt for the trimmer."))
    memory.attach_evidence(alice, fact.id, receipt.id, "Receipt for the trimmer.")
    memory.attach_evidence(alice, fact.id, receipt.id, "Receipt for the trimmer.")
    assert len(memory.facts(alice, entity, known_at=150)[0].evidence) == 1
    assert len(memory.facts(alice, entity)[0].evidence) == 2
    tick[0] = 300
    correction_source = memory.ingest(
        alice, SourceInput(text="It belongs to my brother.")
    )
    correction = FactInput(
        subject_id=entity,
        predicate="owned",
        value=False,
        source_id=correction_source.id,
        operation_key="corrected",
    )
    updated = memory.correct_fact(alice, fact.id, correction)
    assert len(updated.evidence) == 3
    assert memory.correct_fact(alice, fact.id, correction).id == updated.id
    with pytest.raises(MemoryError, match="already corrected"):
        memory.correct_fact(
            alice, fact.id, correction.model_copy(update={"operation_key": "again"})
        )
    assert memory.facts(alice, entity, known_at=150)[0].value is True
    assert memory.facts(alice, entity)[0].value is False


def test_bounded_search_pagination_and_export(tmp_path: Path) -> None:
    _, memory, alice, bob = setup(tmp_path)
    for index in range(4):
        item(memory, alice, f"Husqvarna trimmer {index}")
    item(memory, bob, "Husqvarna private")
    first = memory.list_entities(alice, limit=2)
    second = memory.list_entities(alice, cursor=first["next_cursor"], limit=2)
    assert len({entry.id for entry in first["items"] + second["items"]}) == 4
    assert second["next_cursor"] is None
    assert len(memory.search(alice, "Husqvarna", limit=2)) == 2
    assert memory.search(alice, "private") == []
    assert len(memory.export_page(alice, "entities")["items"]) == 4
    assert all(
        "user_id" not in row for row in memory.export_page(alice, "sources")["items"]
    )
    operations: list[Callable[[], object]] = [
        lambda: memory.search(alice, ""),
        lambda: memory.search(alice, "x" * 201),
        lambda: memory.search(alice, "a " * 13),
        lambda: memory.search(alice, "---"),
        lambda: memory.list_entities(alice, limit=101),
        lambda: memory.related(alice, first["items"][0].id, depth=3),
    ]
    for operation in operations:
        with pytest.raises(MemoryError):
            operation()
    # Treat punctuation/operators as literal tokens, never arbitrary FTS syntax.
    memory.search(alice, '"Husqvarna" OR (*')


def test_concurrent_replay_and_snapshot_restore(tmp_path: Path) -> None:
    auth, memory, alice, bob = setup(tmp_path)
    source_input = SourceInput(
        text="One synthetic receipt.", source_type="receipt", external_id="receipt-1"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(
            pool.map(lambda _: memory.ingest(alice, source_input).id, range(8))
        )
    assert len(set(identifiers)) == 1
    assert memory.ingest(bob, source_input).id != identifiers[0]
    with Session(auth.engine) as db:
        assert (
            len(list(db.scalars(select(Episode).where(Episode.user_id == alice.id))))
            == 1
        )
    entity = memory.create_entity(
        alice,
        EntityInput(
            name="Trimmer",
            kind="asset",
            source_id=identifiers[0],
            operation_key="trimmer",
        ),
    )
    memory.assert_fact(
        alice,
        FactInput(
            subject_id=entity.id,
            predicate="owned",
            value=True,
            source_id=identifiers[0],
            operation_key="owned",
        ),
    )
    path = tmp_path / "snapshot.jsonl"
    operator_snapshot(auth.engine, path)
    with pytest.raises(FileExistsError):
        operator_snapshot(auth.engine, path)
    restored = AuthStore(restore_copy(path))
    restored.migrate()
    recovered = MemoryService(restored.engine)
    assert recovered.get_entity(alice, entity.id).name == "Trimmer"
    assert recovered.facts(alice, entity.id)[0].value is True
    assert recovered.search(alice, "receipt")
    assert recovered.list_entities(bob)["items"] == []


def test_fact_pagination_cycles_and_invalid_world_dates(tmp_path: Path) -> None:
    _, memory, alice, bob = setup(tmp_path)
    first, source = item(memory, alice, "first")
    second, _ = item(memory, alice, "second")
    third, _ = item(memory, alice, "third")
    for index, (subject, target) in enumerate(
        [(first, second), (second, third), (third, first)]
    ):
        memory.assert_fact(
            alice,
            FactInput(
                subject_id=subject,
                predicate="related_to",
                object_id=target,
                source_id=source,
                operation_key=f"edge-{index}",
            ),
        )
    for index in range(3):
        memory.assert_fact(
            alice,
            FactInput(
                subject_id=first,
                predicate="note",
                value=index,
                source_id=source,
                operation_key=f"note-{index}",
            ),
        )
    page = memory.timeline(alice, first, limit=2)
    following = memory.timeline(alice, first, limit=2, cursor=page[-1].id)
    assert len({fact.id for fact in page + following}) == 4
    current_page = memory.facts(alice, first, limit=2)
    assert len(memory.facts(alice, first, limit=2, cursor=current_page[-1].id)) == 2
    graph = memory.related(alice, first, depth=2)
    assert len(graph["nodes"]) == 3 and len(graph["edges"]) == 3
    assert memory.related(alice, first, limit=1)["truncated"] is True
    with pytest.raises(MemoryError):
        memory.facts(alice, first, world_date="not-a-date")
    with pytest.raises(MemoryError):
        memory.timeline(bob, first, cursor=page[-1].id)
