from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import text

from lifegather.auth.store import Account, AuthStore
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.schemas import DiscoveryInput, OrderRef
from lifegather.reconciliation.service import ReconciliationService


def setup(
    tmp_path: Path,
) -> tuple[AuthStore, Account, Account, MemoryService, ReconciliationService]:
    store = AuthStore(tmp_path / "test.sqlite3")
    store.migrate()
    alice = store.login("a", "a@example.test", "A", now=1).user
    bob = store.login("b", "b@example.test", "B", now=1).user
    memory = MemoryService(store.engine)
    return store, alice, bob, memory, ReconciliationService(store.engine)


def discovery(
    memory: MemoryService,
    actor: Account,
    *,
    key: str = "receipt",
    order: str | None = "A100",
    quantity: int = 1,
    serial: str | None = None,
    kind: Literal["purchase", "possession", "mention", "payment"] = "purchase",
    model: str = "525L",
) -> DiscoveryInput:
    quote = f"Home Depot order {order}, line 1: {quantity} Husqvarna {model} trimmer"
    if serial:
        quote += f" serial {serial}"
    source = memory.ingest(actor, SourceInput(text=quote, external_id=key))
    return DiscoveryInput(
        source_id=source.id,
        item_key="line1",
        name="trimmer",
        manufacturer="Husqvarna",
        model=model,
        serial=serial,
        quantity=quantity,
        order=OrderRef(
            retailer="Home Depot", account_scope="mine", order_id=order, line_id="1"
        )
        if order
        else None,
        kind=kind,
        quote=quote,
    )


def test_receipt_shipping_replay_and_distinct_orders(tmp_path: Path) -> None:
    store, actor, _, memory, reconcile = setup(tmp_path)
    first = discovery(memory, actor)
    created = reconcile.discover(actor, first)
    assert created.outcome == "create"
    assert reconcile.discover(actor, first) == created
    shipping = reconcile.discover(actor, discovery(memory, actor, key="shipping"))
    assert shipping.outcome == "enrich"
    assert shipping.asset_ids == created.asset_ids
    second = reconcile.discover(
        actor, discovery(memory, actor, key="other", order="A101")
    )
    assert second.outcome == "create"
    assert second.asset_ids != created.asset_ids
    assert len(reconcile.inventory(actor)) == 2
    facts = memory.facts(actor, created.asset_ids[0])
    assert all(f.status == "inferred" for f in facts if f.predicate == "owned")
    assert all(f.valid_from is None for f in facts)
    assert {e["source_id"] for f in facts for e in f.evidence} >= {first.source_id}
    with store.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM reconciliation_purchases"))
            == 2
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM memory_entities WHERE kind='product'")
            )
            == 1
        )


def test_ambiguous_manual_receipt_requires_review_and_replay_respects_choice(
    tmp_path: Path,
) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    manual = reconcile.discover(
        actor, discovery(memory, actor, key="manual", order=None)
    )
    candidate = discovery(memory, actor, key="receipt")
    review = reconcile.discover(actor, candidate)
    assert review.outcome == "review"
    assert review.asset_ids == []
    assert review.candidate_ids == manual.asset_ids
    assert len(reconcile.reviews(actor)) == 1
    resolved = reconcile.resolve(
        actor, review.id, review.decision_id, asset_ids=manual.asset_ids
    )
    assert resolved.asset_ids == manual.asset_ids
    assert (
        reconcile.resolve(
            actor, review.id, review.decision_id, asset_ids=manual.asset_ids
        )
        == resolved
    )
    assert reconcile.discover(actor, candidate) == resolved
    assert reconcile.reviews(actor) == []
    assert len(reconcile.inventory(actor)) == 1
    undone = reconcile.undo(actor, resolved.decision_id)
    assert undone.outcome == "review"
    assert reconcile.undo(actor, resolved.decision_id) == undone
    assert reconcile.discover(actor, candidate) == undone


def test_quantities_serials_payment_and_conflicts(tmp_path: Path) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    multi = reconcile.discover(actor, discovery(memory, actor, quantity=2))
    assert len(set(multi.asset_ids)) == 2
    assert (
        reconcile.discover(
            actor, discovery(memory, actor, key="shipment", quantity=2)
        ).asset_ids
        == multi.asset_ids
    )
    assert (
        reconcile.discover(
            actor, discovery(memory, actor, key="wrongqty", quantity=1)
        ).outcome
        == "review"
    )
    assert (
        reconcile.discover(
            actor, discovery(memory, actor, key="wrongmodel", model="999")
        ).outcome
        == "review"
    )
    paid = reconcile.discover(
        actor, discovery(memory, actor, key="bank", order="B", kind="payment")
    )
    assert paid.outcome == "review" and paid.asset_ids == []
    serial = reconcile.discover(
        actor, discovery(memory, actor, key="serial1", order="S", serial="SN123")
    )
    match = reconcile.discover(
        actor, discovery(memory, actor, key="serial2", order=None, serial="SN123")
    )
    assert match.asset_ids == serial.asset_ids


def test_owner_scope_validation_and_atomic_failure(tmp_path: Path) -> None:
    store, actor, bob, memory, reconcile = setup(tmp_path)
    first = discovery(memory, actor)
    result = reconcile.discover(actor, first)
    with pytest.raises(MemoryError):
        reconcile.discover(bob, first)
    with pytest.raises(MemoryError):
        reconcile.resolve(
            bob, result.id, result.decision_id, asset_ids=result.asset_ids
        )
    assert reconcile.inventory(bob) == [] and reconcile.reviews(bob) == []
    changed = first.model_copy(update={"name": "invented"})
    with pytest.raises(MemoryError):
        reconcile.discover(actor, changed)
    with pytest.raises(MemoryError):
        reconcile.discover(actor, first.model_copy(update={"quote": "not in source"}))
    own_bob = reconcile.discover(bob, discovery(memory, bob))
    with pytest.raises(MemoryError):
        reconcile.resolve(
            actor, result.id, result.decision_id, asset_ids=own_bob.asset_ids
        )
    assert reconcile.discover(actor, first) == result
    with store.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_reassociation_undo_and_stale_decisions(tmp_path: Path) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    one = reconcile.discover(actor, discovery(memory, actor))
    two = reconcile.discover(actor, discovery(memory, actor, key="two", order="B"))
    changed = reconcile.resolve(actor, two.id, two.decision_id, asset_ids=one.asset_ids)
    assert len(reconcile.inventory(actor)) == 1
    with pytest.raises(MemoryError):
        reconcile.resolve(actor, two.id, two.decision_id, asset_ids=None)
    restored = reconcile.undo(actor, changed.decision_id)
    assert restored.asset_ids == two.asset_ids
    assert len(reconcile.inventory(actor)) == 2
    assert memory.get_source(actor, discovery(memory, actor).source_id).text
    assert memory.timeline(actor, two.asset_ids[0])


def test_concurrent_replays_restore_and_dismissal(tmp_path: Path) -> None:
    store, actor, _, memory, reconcile = setup(tmp_path)
    value = discovery(memory, actor)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reconcile.discover(actor, value), range(8)))
    assert len({r.id for r in results}) == 1
    result = results[0]
    dismissed = reconcile.dismiss(actor, result.id, result.decision_id)
    assert reconcile.inventory(actor) == []
    assert reconcile.discover(actor, value) == dismissed
    assert reconcile.undo(actor, dismissed.decision_id).asset_ids == result.asset_ids
    snapshot = tmp_path / "snapshot.sqlite3"
    operator_snapshot(store.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert (
        ReconciliationService(restored.engine).discover(actor, value).asset_ids
        == result.asset_ids
    )


@pytest.mark.parametrize(
    "sequence",
    [
        ("manual", "receipt", "shipment"),
        ("receipt", "shipment", "manual"),
        ("shipment", "manual", "receipt"),
    ],
)
def test_source_order_does_not_change_physical_identity(
    tmp_path: Path, sequence: tuple[str, str, str]
) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    results = [
        reconcile.discover(
            actor,
            discovery(
                memory,
                actor,
                key=kind,
                order=None if kind == "manual" else "A100",
                serial="UNIQUE",
            ),
        )
        for kind in sequence
    ]
    assert len({tuple(row.asset_ids) for row in results}) == 1
    assert len(reconcile.inventory(actor)) == 1


def test_excluded_serial_does_not_silently_reappear(tmp_path: Path) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    first = discovery(memory, actor, serial="SN123")
    created = reconcile.discover(actor, first)
    reconcile.dismiss(actor, created.id, created.decision_id)
    quote = "Husqvarna 525L weed eater serial SN123"
    source = memory.ingest(actor, SourceInput(text=quote))
    other = DiscoveryInput(
        source_id=source.id,
        item_key="item",
        name="weed eater",
        manufacturer="Husqvarna",
        model="525L",
        serial="SN123",
        quantity=1,
        kind="possession",
        quote=quote,
    )
    review = reconcile.discover(actor, other)
    assert review.outcome == "review" and review.asset_ids == []
    assert created.asset_ids[0] in review.candidate_ids
    assert reconcile.inventory(actor) == []


def test_concurrent_distinct_sources_share_units_and_export_is_private(
    tmp_path: Path,
) -> None:
    _, actor, bob, memory, reconcile = setup(tmp_path)
    values = [discovery(memory, actor, key=f"copy-{i}", quantity=2) for i in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda value: reconcile.discover(actor, value), values))
    assert len({tuple(row.asset_ids) for row in rows}) == 1
    assert len(reconcile.inventory(actor)) == 2
    collections: tuple[
        Literal[
            "purchases", "lines", "observations", "decisions", "bindings", "candidates"
        ],
        ...,
    ] = ("purchases", "lines", "observations", "decisions", "bindings", "candidates")
    for collection in collections:
        assert reconcile.export_page(bob, collection)["items"] == []
    page = reconcile.export_page(actor, "observations", limit=3)
    assert len(page["items"]) == 3 and page["next_cursor"]
    assert (
        len(
            reconcile.export_page(actor, "observations", cursor=page["next_cursor"])[
                "items"
            ]
        )
        == 5
    )
    with pytest.raises(MemoryError):
        reconcile.inventory(actor, limit=101)
    with pytest.raises(MemoryError):
        reconcile.history(bob, rows[0].id)


def test_database_owner_constraints_and_non_asset_rollback(tmp_path: Path) -> None:
    from uuid import uuid4

    from sqlalchemy import insert, select
    from sqlalchemy.exc import IntegrityError

    from lifegather.memory.schemas import EntityInput
    from lifegather.reconciliation.models import (
        Binding,
        Candidate,
        Decision,
        Observation,
        Purchase,
        PurchaseLine,
    )

    store, actor, bob, memory, reconcile = setup(tmp_path)
    value = discovery(memory, actor)
    row = reconcile.discover(actor, value)
    for model in (Purchase, PurchaseLine, Observation, Decision, Binding):
        with store.engine.connect() as connection:
            original = dict(
                connection.execute(select(model.__table__).limit(1)).mappings().one()
            )
        original.update(id=str(uuid4()), user_id=bob.id)
        with pytest.raises(IntegrityError), store.engine.begin() as connection:
            connection.execute(insert(model).values(**original))
    with pytest.raises(IntegrityError), store.engine.begin() as connection:
        connection.execute(
            insert(Candidate).values(
                id=str(uuid4()),
                user_id=bob.id,
                recorded_at=1,
                decision_id=row.decision_id,
                asset_id=row.asset_ids[0],
            )
        )
    product = memory.create_entity(
        actor,
        EntityInput(
            name="Husqvarna 525L",
            kind="product",
            source_id=value.source_id,
            operation_key="other-product",
        ),
    )
    before = memory.facts(actor, row.asset_ids[0])
    with pytest.raises(MemoryError):
        reconcile.resolve(actor, row.id, row.decision_id, asset_ids=[product.id])
    assert reconcile.get(actor, row.id) == row
    assert memory.facts(actor, row.asset_ids[0]) == before
    assert len(reconcile.history(actor, row.id)) == 1


def test_partial_write_failure_rolls_back_all_derived_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.orm import Session

    from lifegather.memory.schemas import FactInput, FactView

    store, actor, _, memory, reconcile = setup(tmp_path)
    value = discovery(memory, actor)
    original = reconcile.memory._put_fact_in

    def fail(
        db: Session,
        who: Account,
        data: FactInput,
        replaces: str | None,
        *,
        recorded_at: int | None = None,
    ) -> FactView:
        original(db, who, data, replaces, recorded_at=recorded_at)
        raise MemoryError("Synthetic failure after fact write")

    monkeypatch.setattr(reconcile.memory, "_put_fact_in", fail)
    with pytest.raises(MemoryError):
        reconcile.discover(actor, value)
    with store.engine.connect() as connection:
        for table in (
            "memory_entities",
            "memory_facts",
            "memory_evidence",
            "reconciliation_purchases",
            "reconciliation_lines",
            "reconciliation_observations",
            "reconciliation_decisions",
            "reconciliation_bindings",
        ):
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM " + table).scalar()
                == 0
            )
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM memory_fts WHERE kind='entity'"
            ).scalar()
            == 0
        )


def test_validation_and_review_history_pagination(tmp_path: Path) -> None:
    from pydantic import ValidationError

    _, actor, _, memory, reconcile = setup(tmp_path)
    value = discovery(memory, actor)
    for patch in (
        {"quantity": True},
        {"quantity": 21},
        {"serial": "SN", "quantity": 2},
        {"name": " "},
    ):
        with pytest.raises(ValidationError):
            reconcile.discover(actor, value.model_copy(update=patch))
    created = reconcile.discover(actor, value)
    dismissed = reconcile.dismiss(actor, created.id, created.decision_id)
    restored = reconcile.undo(actor, dismissed.decision_id)
    history = reconcile.history(actor, created.id, limit=1)
    assert history[0].decision_id == created.decision_id
    assert (
        reconcile.history(actor, created.id, cursor=history[0].decision_id)[
            -1
        ].decision_id
        == restored.decision_id
    )
    assert restored.previous_decision_id == dismissed.decision_id


def test_prior_memory_alias_prevents_duplicate_and_upgrade_preserves_data(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather
    from lifegather.memory.schemas import EntityInput, FactInput

    store = AuthStore(tmp_path / "old.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003_memory_core")
    from sqlalchemy.orm import Session

    from lifegather.auth.models import User

    with Session(store.engine) as db, db.begin():
        legacy = User(
            id="legacy-user",
            issuer="https://accounts.google.com",
            subject="a",
            email="a@example.test",
            name="A",
            created_at=100,
        )
        db.add(legacy)
        db.flush()
        session = store.issue_session(db, legacy, 100)
    actor = session.user
    memory = MemoryService(store.engine)
    source = memory.ingest(actor, SourceInput(text="My weed eater is a trimmer."))
    item = memory.create_entity(
        actor,
        EntityInput(
            name="weed eater",
            kind="asset",
            source_id=source.id,
            operation_key="manual-item",
        ),
    )
    memory.add_alias(actor, item.id, "trimmer", source.id)
    old_fact = memory.assert_fact(
        actor,
        FactInput(
            subject_id=item.id,
            predicate="owned",
            value=True,
            source_id=source.id,
            operation_key="owned",
        ),
    )
    store.migrate()
    assert store.authenticate(session.token, now=101) is not None
    assert memory.facts(actor, item.id)[0].id == old_fact.id
    result = ReconciliationService(store.engine).discover(
        actor, discovery(memory, actor)
    )
    assert result.outcome == "review" and result.candidate_ids == [item.id]
    with store.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_decision_and_fact_times_survive_a_backward_clock(tmp_path: Path) -> None:
    _, actor, _, memory, reconcile = setup(tmp_path)
    value = discovery(memory, actor)
    reconcile.memory.clock = lambda: 1
    created = reconcile.discover(actor, value)
    facts = memory.facts(actor, created.asset_ids[0])
    assert all(f.recorded_at == created.recorded_at for f in facts)
    dismissed = reconcile.dismiss(actor, created.id, created.decision_id)
    restored = reconcile.undo(actor, dismissed.decision_id)
    assert restored.recorded_at > dismissed.recorded_at > created.recorded_at
    assert (
        memory.facts(actor, created.asset_ids[0], known_at=dismissed.recorded_at) == []
    )
    assert all(
        f.recorded_at == restored.recorded_at
        for f in memory.facts(actor, created.asset_ids[0])
    )


def test_new_receipt_does_not_override_a_sale_or_ownership_correction(
    tmp_path: Path,
) -> None:
    from lifegather.memory.schemas import FactInput

    _, actor, _, memory, reconcile = setup(tmp_path)
    created = reconcile.discover(actor, discovery(memory, actor))
    source = memory.ingest(actor, SourceInput(text="I sold my trimmer."))
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=created.asset_ids[0],
            predicate="owned",
            value=False,
            source_id=source.id,
            operation_key="sold",
        ),
    )
    later = reconcile.discover(actor, discovery(memory, actor, key="older-order-copy"))
    assert later.outcome == "review" and later.asset_ids == []
    assert later.candidate_ids == created.asset_ids
