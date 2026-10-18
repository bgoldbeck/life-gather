"""Deterministic reconciliation of validated evidence, independent of AI and HTTP."""

from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Entity
from lifegather.memory.schemas import EntityInput, FactInput
from lifegather.memory.service import (
    MemoryError,
    MemoryService,
    bounded,
    fingerprint,
    normalized,
)
from lifegather.reconciliation.matching import IdentityMatcher
from lifegather.reconciliation.models import (
    Binding,
    Candidate,
    Decision,
    Observation,
    Purchase,
    PurchaseLine,
)
from lifegather.reconciliation.schemas import DiscoveryInput, DiscoveryView


class ReconciliationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.matcher = IdentityMatcher()

    @staticmethod
    def _observation(db: Session, actor: Account, identifier: str) -> Observation:
        row = db.scalar(
            select(Observation)
            .where(Observation.user_id == actor.id, Observation.id == identifier)
            .limit(1)
        )
        if row is None:
            raise MemoryError("Discovery not found")
        return row

    @staticmethod
    def _decision(db: Session, actor: Account, identifier: str) -> Decision:
        row = db.scalar(
            select(Decision)
            .where(Decision.user_id == actor.id, Decision.id == identifier)
            .limit(1)
        )
        if row is None:
            raise MemoryError("Decision not found")
        return row

    @staticmethod
    def _current(db: Session, actor: Account, observation_id: str) -> Decision:
        row = db.scalar(
            select(Decision)
            .where(
                Decision.user_id == actor.id,
                Decision.observation_id == observation_id,
                Decision.superseded_at.is_(None),
            )
            .limit(1)
        )
        if row is None:
            raise MemoryError("Decision not found")
        return row

    @staticmethod
    def _bindings(db: Session, actor: Account, decision_id: str) -> list[Binding]:
        return list(
            db.scalars(
                select(Binding)
                .where(Binding.user_id == actor.id, Binding.decision_id == decision_id)
                .order_by(Binding.unit)
                .limit(20)
            )
        )

    def _view(self, db: Session, actor: Account, row: Decision) -> DiscoveryView:
        return DiscoveryView(
            id=row.observation_id,
            decision_id=row.id,
            outcome=row.outcome,
            reason=row.reason,
            recorded_at=row.recorded_at,
            superseded_at=row.superseded_at,
            previous_decision_id=row.previous_id,
            asset_ids=[
                binding.asset_id for binding in self._bindings(db, actor, row.id)
            ],
            candidate_ids=list(
                db.scalars(
                    select(Candidate.asset_id)
                    .where(
                        Candidate.user_id == actor.id, Candidate.decision_id == row.id
                    )
                    .order_by(Candidate.asset_id)
                    .limit(100)
                )
            ),
        )

    def get(self, actor: Account, observation_id: str) -> DiscoveryView:
        with Session(self.engine) as db:
            self._observation(db, actor, observation_id)
            return self._view(db, actor, self._current(db, actor, observation_id))

    def _product(self, db: Session, actor: Account, data: DiscoveryInput) -> str | None:
        if not data.manufacturer or not data.model:
            return None
        key = fingerprint([normalized(data.manufacturer), normalized(data.model)])
        existing = db.scalar(
            select(Entity.id)
            .where(
                Entity.user_id == actor.id,
                Entity.operation_key == "reconcile:product:" + key,
            )
            .limit(1)
        )
        if existing:
            return existing
        return self.memory._create_entity_in(
            db,
            actor,
            EntityInput(
                name=f"{data.manufacturer} {data.model}"[:200],
                kind="product",
                source_id=data.source_id,
                operation_key="reconcile:product:" + key,
            ),
        ).id

    def _line(
        self, db: Session, actor: Account, data: DiscoveryInput, product_id: str | None
    ) -> tuple[str | None, bool]:
        order = data.order
        if order is None or data.kind in {"payment", "mention"}:
            return None, False
        key = fingerprint(
            [normalized(order.retailer), order.account_scope, order.order_id]
        )
        purchase = db.scalar(
            select(Purchase)
            .where(Purchase.user_id == actor.id, Purchase.identity_key == key)
            .limit(1)
        )
        now = self.memory.clock()
        if purchase is None:
            purchase = Purchase(
                id=str(uuid4()),
                user_id=actor.id,
                recorded_at=now,
                identity_key=key,
                retailer=order.retailer,
                account_scope=order.account_scope,
                order_id=order.order_id,
                source_id=data.source_id,
            )
            db.add(purchase)
            db.flush()
        line = db.scalar(
            select(PurchaseLine)
            .where(
                PurchaseLine.user_id == actor.id,
                PurchaseLine.purchase_id == purchase.id,
                PurchaseLine.line_key == order.line_id,
            )
            .limit(1)
        )
        if line is not None:
            return line.id, line.quantity != data.quantity or (
                line.product_id is not None
                and product_id is not None
                and line.product_id != product_id
            )
        line = PurchaseLine(
            id=str(uuid4()),
            user_id=actor.id,
            recorded_at=now,
            purchase_id=purchase.id,
            line_key=order.line_id,
            product_id=product_id,
            quantity=data.quantity,
            source_id=data.source_id,
        )
        db.add(line)
        db.flush()
        return line.id, False

    def discover(self, actor: Account, value: DiscoveryInput) -> DiscoveryView:
        data = DiscoveryInput.model_validate(value)
        signature = fingerprint(data.model_dump(mode="json"))
        with self.memory._write() as db:
            source = self.memory._source(db, actor, data.source_id)
            if data.quote not in source.text:
                raise MemoryError("Discovery quote must appear in its source")
            fields = [data.name, data.manufacturer, data.model, data.serial]
            if data.order:
                fields.extend(
                    [data.order.retailer, data.order.order_id, data.order.line_id]
                )
            if any(
                field and normalized(field) not in normalized(data.quote)
                for field in fields
            ):
                raise MemoryError("Identity fields must appear in discovery evidence")
            existing = db.scalar(
                select(Observation)
                .where(
                    Observation.user_id == actor.id,
                    Observation.source_id == data.source_id,
                    Observation.item_key == data.item_key,
                )
                .limit(1)
            )
            if existing:
                if existing.fingerprint != signature:
                    raise MemoryError(
                        "Discovery replay conflict; use a new source revision"
                    )
                return self._view(db, actor, self._current(db, actor, existing.id))
            if source.source_type == "statement" and data.kind != "payment":
                raise MemoryError("Bank statements cannot establish item contents")
            product_id = (
                self._product(db, actor, data)
                if data.kind not in {"payment", "mention"}
                else None
            )
            line_id, conflict = self._line(db, actor, data, product_id)
            observation = Observation(
                id=str(uuid4()),
                user_id=actor.id,
                recorded_at=max(self.memory.clock(), source.recorded_at),
                source_id=data.source_id,
                item_key=data.item_key,
                payload=data.model_dump_json(),
                fingerprint=signature,
                product_id=product_id,
                line_id=line_id,
                serial_key=fingerprint(
                    [normalized(data.manufacturer or ""), data.serial.strip()]
                )
                if data.serial
                else None,
            )
            db.add(observation)
            db.flush()
            outcome, reason, targets, candidates = self.matcher._choose(
                db, actor, observation, data, conflict
            )
            return self._record(
                db,
                actor,
                observation,
                outcome,
                reason,
                targets,
                candidates,
                "discover",
                None,
            )

    def _record(
        self,
        db: Session,
        actor: Account,
        observation: Observation,
        outcome: str,
        reason: str,
        targets: list[str],
        candidates: list[str],
        request_key: str,
        previous: Decision | None,
    ) -> DiscoveryView:
        data = DiscoveryInput.model_validate_json(observation.payload)
        now = max(
            self.memory.clock(),
            previous.recorded_at + 1 if previous else observation.recorded_at,
        )
        if previous:
            previous.superseded_at = now
            for binding in self._bindings(db, actor, previous.id):
                for fact_id in (binding.ownership_fact_id, binding.product_fact_id):
                    if fact_id:
                        fact = self.memory._assertion(db, actor, fact_id)
                        if fact.superseded_at is None:
                            fact.superseded_at = max(now, fact.recorded_at + 1)
            db.flush()
        decision = Decision(
            id=str(uuid4()),
            user_id=actor.id,
            recorded_at=now,
            observation_id=observation.id,
            previous_id=previous.id if previous else None,
            outcome=outcome,
            reason=reason,
            request_key=request_key,
            superseded_at=None,
        )
        db.add(decision)
        db.flush()
        if outcome == "create" and not targets:
            targets = [
                self.memory._create_entity_in(
                    db,
                    actor,
                    EntityInput(
                        name=data.name,
                        kind="asset",
                        source_id=data.source_id,
                        operation_key=f"reconcile:asset:{decision.id}:{unit}",
                    ),
                    recorded_at=now,
                ).id
                for unit in range(data.quantity)
            ]
        for unit, asset_id in enumerate(targets):
            entity = self.memory._entity(db, actor, asset_id)
            if entity.kind != "asset":
                raise MemoryError("Discovery target must be a physical asset")
            owned = self.memory._put_fact_in(
                db,
                actor,
                FactInput(
                    subject_id=asset_id,
                    predicate="owned",
                    value=True,
                    status="inferred",
                    source_id=data.source_id,
                    quote=data.quote,
                    operation_key=f"reconcile:{decision.id}:{unit}:owned",
                ),
                None,
                recorded_at=now,
            )
            product_fact = (
                self.memory._put_fact_in(
                    db,
                    actor,
                    FactInput(
                        subject_id=asset_id,
                        predicate="product_model",
                        object_id=observation.product_id,
                        status="stated",
                        source_id=data.source_id,
                        quote=data.quote,
                        operation_key=f"reconcile:{decision.id}:{unit}:product",
                    ),
                    None,
                    recorded_at=now,
                )
                if observation.product_id
                else None
            )
            db.add(
                Binding(
                    id=str(uuid4()),
                    user_id=actor.id,
                    recorded_at=now,
                    decision_id=decision.id,
                    unit=unit,
                    asset_id=asset_id,
                    ownership_fact_id=owned.id,
                    product_fact_id=product_fact.id if product_fact else None,
                )
            )
        for candidate in sorted(set(candidates))[:100]:
            self.memory._entity(db, actor, candidate)
            db.add(
                Candidate(
                    id=str(uuid4()),
                    user_id=actor.id,
                    recorded_at=now,
                    decision_id=decision.id,
                    asset_id=candidate,
                )
            )
        self.memory._audit(db, actor, "discovery_" + outcome, observation.id, now)
        db.flush()
        return self._view(db, actor, decision)

    def _change(
        self,
        actor: Account,
        observation_id: str,
        expected: str,
        action: Literal["resolve", "dismiss", "undo"],
        asset_ids: list[str] | None,
    ) -> DiscoveryView:
        if asset_ids is not None and (
            not 1 <= len(asset_ids) <= 20 or len(asset_ids) != len(set(asset_ids))
        ):
            raise MemoryError("Supply 1 to 20 distinct physical items")
        key = fingerprint([action, asset_ids])
        with self.memory._write() as db:
            observation = self._observation(db, actor, observation_id)
            old = self._decision(db, actor, expected)
            if old.observation_id != observation.id:
                raise MemoryError("Decision does not belong to discovery")
            successor = db.scalar(
                select(Decision)
                .where(Decision.user_id == actor.id, Decision.previous_id == old.id)
                .limit(1)
            )
            if successor:
                if successor.request_key == key:
                    return self._view(db, actor, successor)
                raise MemoryError("Stale decision; reload discovery")
            current = self._current(db, actor, observation_id)
            if current.id != old.id:
                raise MemoryError("Stale decision; reload discovery")
            data = DiscoveryInput.model_validate_json(observation.payload)
            if action == "undo":
                predecessor = (
                    self._decision(db, actor, old.previous_id)
                    if old.previous_id
                    else None
                )
                if predecessor:
                    prior = self._view(db, actor, predecessor)
                    return self._record(
                        db,
                        actor,
                        observation,
                        prior.outcome,
                        "Restored preceding decision",
                        prior.asset_ids,
                        prior.candidate_ids,
                        key,
                        old,
                    )
                return self._record(
                    db,
                    actor,
                    observation,
                    "review",
                    "Automatic decision undone; awaiting correction",
                    [],
                    [],
                    key,
                    old,
                )
            if action == "dismiss":
                return self._record(
                    db,
                    actor,
                    observation,
                    "dismissed",
                    "User excluded this discovery from inventory",
                    [],
                    [],
                    key,
                    old,
                )
            if data.kind in {"payment", "mention"}:
                raise MemoryError(
                    "Create a possession source before adding this to inventory"
                )
            if asset_ids is not None and len(asset_ids) != data.quantity:
                raise MemoryError("Choose one distinct physical item for each unit")
            for identifier in asset_ids or []:
                self.memory._entity(db, actor, identifier)
            return self._record(
                db,
                actor,
                observation,
                "enrich" if asset_ids else "create",
                "User resolved physical identity",
                asset_ids or [],
                [],
                key,
                old,
            )

    def resolve(
        self,
        actor: Account,
        observation_id: str,
        expected_decision_id: str,
        *,
        asset_ids: list[str] | None,
    ) -> DiscoveryView:
        return self._change(
            actor, observation_id, expected_decision_id, "resolve", asset_ids
        )

    def dismiss(
        self, actor: Account, observation_id: str, expected_decision_id: str
    ) -> DiscoveryView:
        return self._change(
            actor, observation_id, expected_decision_id, "dismiss", None
        )

    def undo(self, actor: Account, decision_id: str) -> DiscoveryView:
        with Session(self.engine) as db:
            row = self._decision(db, actor, decision_id)
            observation_id = row.observation_id
        return self._change(actor, observation_id, decision_id, "undo", None)

    def inventory(self, actor: Account, cursor: str = "", limit: int = 25) -> list[str]:
        bounded(limit)
        if len(cursor) > 36:
            raise MemoryError("Invalid inventory cursor")
        with Session(self.engine) as db:
            return list(
                db.scalars(
                    self.matcher._active_bindings(actor)
                    .with_only_columns(Binding.asset_id)
                    .where(Binding.asset_id > cursor)
                    .distinct()
                    .order_by(Binding.asset_id)
                    .limit(limit)
                )
            )

    def reviews(
        self, actor: Account, cursor: str = "", limit: int = 25
    ) -> list[DiscoveryView]:
        bounded(limit)
        if len(cursor) > 36:
            raise MemoryError("Invalid review cursor")
        with Session(self.engine) as db:
            rows = db.scalars(
                select(Decision)
                .where(
                    Decision.user_id == actor.id,
                    Decision.outcome == "review",
                    Decision.superseded_at.is_(None),
                    Decision.observation_id > cursor,
                )
                .order_by(Decision.observation_id)
                .limit(limit)
            )
            return [self._view(db, actor, row) for row in rows]

    def history(
        self, actor: Account, observation_id: str, cursor: str = "", limit: int = 25
    ) -> list[DiscoveryView]:
        bounded(limit)
        if len(cursor) > 36:
            raise MemoryError("Invalid decision cursor")
        with Session(self.engine) as db:
            self._observation(db, actor, observation_id)
            query = select(Decision).where(
                Decision.user_id == actor.id, Decision.observation_id == observation_id
            )
            if cursor:
                prior = self._decision(db, actor, cursor)
                if prior.observation_id != observation_id:
                    raise MemoryError("Invalid history cursor")
                query = query.where(
                    or_(
                        Decision.recorded_at > prior.recorded_at,
                        and_(
                            Decision.recorded_at == prior.recorded_at,
                            Decision.id > prior.id,
                        ),
                    )
                )
            rows = db.scalars(
                query.order_by(Decision.recorded_at, Decision.id).limit(limit)
            )
            return [self._view(db, actor, row) for row in rows]

    def export_page(
        self,
        actor: Account,
        collection: Literal[
            "purchases", "lines", "observations", "decisions", "bindings", "candidates"
        ],
        cursor: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        bounded(limit)
        models = {
            "purchases": Purchase,
            "lines": PurchaseLine,
            "observations": Observation,
            "decisions": Decision,
            "bindings": Binding,
            "candidates": Candidate,
        }
        if collection not in models or len(cursor) > 36:
            raise MemoryError("Invalid reconciliation export page")
        table = models[collection].__table__
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(table)
                    .where(table.c.user_id == actor.id, table.c.id > cursor)
                    .order_by(table.c.id)
                    .limit(limit + 1)
                ).mappings()
            )
            return {
                "items": [
                    {name: value for name, value in row.items() if name != "user_id"}
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
            }
