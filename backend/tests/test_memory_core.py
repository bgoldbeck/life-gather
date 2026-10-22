from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from database_support import database

from lifegather.auth.store import AuthStore
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService


def test_trimmer_lifecycle_provenance_and_historical_corrections(
    tmp_path: Path,
) -> None:
    auth = AuthStore(database(tmp_path / "memory"))
    auth.migrate()
    actor = auth.login("alice", "a@example.test", "Alice", now=1).user
    tick = [100]
    memory = MemoryService(auth.engine, clock=lambda: tick[0])
    episode = memory.ingest(
        actor,
        SourceInput(
            text="I bought a Husqvarna 525L from Home Depot on May 4, 2024.",
            source_type="manual",
            namespace="fixture",
            external_id="purchase",
        ),
    )
    item = memory.create_entity(
        actor,
        EntityInput(
            name="Husqvarna 525L",
            kind="asset",
            source_id=episode.id,
            operation_key="item-1",
        ),
    )
    owned = memory.assert_fact(
        actor,
        FactInput(
            subject_id=item.id,
            predicate="owned",
            value=True,
            source_id=episode.id,
            quote="I bought a Husqvarna 525L",
            valid_from=date(2024, 5, 4),
            operation_key="ownership",
        ),
    )
    alias_source = memory.ingest(
        actor, SourceInput(text="I call this trimmer my weed eater.")
    )
    memory.add_alias(actor, item.id, "weed eater", alias_source.id)
    assert memory.find_entities(actor, "WEED EATER")[0].id == item.id
    assert memory.get_source(actor, episode.id).text.startswith("I bought")
    tick[0] = 200
    maintenance = memory.ingest(
        actor, SourceInput(text="Cleaned my weed eater carburetor.")
    )
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=item.id,
            predicate="maintenance",
            value="carburetor cleaned",
            source_id=maintenance.id,
            quote="Cleaned my weed eater carburetor.",
            operation_key="service-1",
        ),
    )
    tick[0] = 300
    sale = memory.ingest(actor, SourceInput(text="I sold it on July 1, 2025."))
    memory.correct_fact(
        actor,
        owned.id,
        FactInput(
            subject_id=item.id,
            predicate="owned",
            value=True,
            source_id=sale.id,
            quote="I sold it on July 1, 2025.",
            valid_from=date(2024, 5, 4),
            valid_to=date(2025, 7, 1),
            operation_key="ownership-close",
        ),
    )
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=item.id,
            predicate="owned",
            value=False,
            source_id=sale.id,
            quote="I sold it on July 1, 2025.",
            valid_from=date(2025, 7, 1),
            operation_key="sold",
        ),
    )
    assert memory.facts(actor, item.id, world_date="2025-06-01")[0].value is True
    assert memory.facts(actor, item.id, world_date="2025-08-01")[0].value is False
    assert (
        memory.facts(actor, item.id, world_date="2025-08-01", known_at=150)[0].id
        == owned.id
    )
    assert len(memory.timeline(actor, item.id)) == 4
    assert len(memory.search(actor, "weed eater")) >= 1


def test_retries_distinct_items_and_owner_boundaries(tmp_path: Path) -> None:
    auth = AuthStore(database(tmp_path / "memory"))
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "Alice", now=1).user
    bob = auth.login("bob", "b@example.test", "Bob", now=1).user
    memory = MemoryService(auth.engine)
    source = SourceInput(text="I own two identical trimmers.", external_id="one")
    episode = memory.ingest(alice, source)
    assert memory.ingest(alice, source).id == episode.id
    with pytest.raises(MemoryError, match="conflict"):
        memory.ingest(alice, source.model_copy(update={"text": "Changed original"}))
    first_input = EntityInput(
        name="Trimmer", kind="asset", source_id=episode.id, operation_key="unit-1"
    )
    first = memory.create_entity(alice, first_input)
    assert memory.create_entity(alice, first_input).id == first.id
    second = memory.create_entity(
        alice, first_input.model_copy(update={"operation_key": "unit-2"})
    )
    assert second.id != first.id
    assert memory.search(bob, "trimmers") == []
    assert memory.list_entities(bob)["items"] == []
    operations: list[Callable[[], object]] = [
        lambda: memory.get_entity(bob, first.id),
        lambda: memory.get_source(bob, episode.id),
        lambda: memory.add_alias(bob, first.id, "mine", episode.id),
        lambda: memory.create_entity(bob, first_input),
        lambda: memory.facts(bob, first.id),
        lambda: memory.related(bob, first.id),
    ]
    for operation in operations:
        with pytest.raises(MemoryError):
            operation()
