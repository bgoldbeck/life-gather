import json
from datetime import UTC, date, datetime
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, exists, or_, select
from sqlalchemy.orm import Session, aliased

from lifegather.assets.models import AssetAction
from lifegather.auth.store import Account
from lifegather.memory.models import Entity
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.reconciliation.models import Binding, Decision
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


class AssetChange(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    asset_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    expected_action_id: str = Field(default="", max_length=36)
    operation: Literal["ownership", "undo", "reassociate"]
    note: str = Field(min_length=1, max_length=2000)
    status: Literal["owned", "sold", "returned", "no_longer_owned"] | None = None
    event_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    decision_id: str | None = Field(default=None, min_length=1, max_length=36)
    target_asset_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.note.strip():
            raise ValueError("Explain the change")
        if self.operation == "ownership":
            if not self.status or self.decision_id or self.target_asset_id:
                raise ValueError("Choose an ownership state")
        elif not self.decision_id or self.status or self.event_date:
            raise ValueError("Choose the current decision")
        if self.operation != "reassociate" and self.target_asset_id:
            raise ValueError("Only reassociation chooses another item")
        if self.target_asset_id == self.asset_id:
            raise ValueError("Choose a different item")
        if (
            self.event_date
            and date.fromisoformat(self.event_date) > datetime.now(UTC).date()
        ):
            raise ValueError("Future ownership changes are not supported")
        return self


class ActionService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.reconcile = ReconciliationService(engine)

    @staticmethod
    def latest(db: Session, actor: Account, asset_id: str) -> AssetAction | None:
        return db.scalar(
            select(AssetAction)
            .where(AssetAction.user_id == actor.id, AssetAction.asset_id == asset_id)
            .order_by(AssetAction.recorded_at.desc(), AssetAction.id.desc())
            .limit(1)
        )

    def _fact(
        self,
        db: Session,
        actor: Account,
        row: AssetAction,
        predicate: str,
        value: str | bool,
        when: date | None,
        previous_id: str | None,
    ) -> str:
        source = self.memory._source(db, actor, row.source_id)
        previous = (
            self.memory._assertion(db, actor, previous_id) if previous_id else None
        )
        if previous and when and previous.valid_from and when < previous.valid_from:
            raise NoteConflict("Event date precedes the latest ownership statement")
        if (
            previous
            and when
            and (previous.valid_from is None or when > previous.valid_from)
        ):
            self.memory._put_fact_in(
                db,
                actor,
                FactInput(
                    subject_id=row.asset_id,
                    predicate=predicate,
                    value=json.loads(previous.value_json or "null"),
                    status="stated",
                    source_id=source.id,
                    quote=source.text,
                    valid_from=previous.valid_from,
                    valid_to=when,
                    operation_key=f"asset-action:{row.id}:{predicate}:close",
                ),
                previous.id,
                recorded_at=row.recorded_at,
            )
            previous_id = None
        result = self.memory._put_fact_in(
            db,
            actor,
            FactInput(
                subject_id=row.asset_id,
                predicate=predicate,
                value=value,
                status="stated",
                source_id=source.id,
                quote=source.text,
                valid_from=when,
                operation_key=f"asset-action:{row.id}:{predicate}",
            ),
            previous_id,
            recorded_at=row.recorded_at,
        )
        return result.id

    def apply(self, actor: Account, value: AssetChange) -> dict[str, Any]:
        data = AssetChange.model_validate(value)
        signature = fingerprint(data.model_dump())
        with self.memory._write() as db:
            asset = self.memory._entity(db, actor, data.asset_id)
            if asset.kind != "asset":
                raise MemoryError("Choose a physical item")
            existing = db.scalar(
                select(AssetAction).where(
                    AssetAction.user_id == actor.id,
                    AssetAction.request_id == data.request_id,
                )
            )
            if existing:
                if existing.fingerprint != signature:
                    raise NoteConflict("Action request conflict")
                return {"id": existing.id, **json.loads(existing.result_json)}
            previous = self.latest(db, actor, asset.id)
            if (previous.id if previous else "") != data.expected_action_id:
                raise NoteConflict("This item changed. Reload it before correcting it.")
            now = max(
                self.memory.clock(),
                previous.recorded_at + 1 if previous else asset.recorded_at,
            )
            if data.decision_id:
                # One transaction timestamp for explanation, decision and audit.
                # Preserve logical order even after a wall-clock adjustment.
                decision = self.reconcile._decision(db, actor, data.decision_id)
                now = max(now, self.reconcile.memory.clock(), decision.recorded_at + 1)
                if data.target_asset_id:
                    target = self.memory._entity(db, actor, data.target_asset_id)
                    now = max(now, target.recorded_at)
            when = date.fromisoformat(data.event_date) if data.event_date else None
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.note,
                    source_type="conversation",
                    namespace="asset-action",
                    external_id=data.request_id,
                    event_date=when,
                ),
                recorded_at=now,
            )
            row = AssetAction(
                id=str(uuid4()),
                user_id=actor.id,
                asset_id=asset.id,
                target_asset_id=data.target_asset_id,
                previous_id=previous.id if previous else None,
                source_id=source.id,
                request_id=data.request_id,
                fingerprint=signature,
                operation=data.operation,
                ownership_fact_id=None,
                status_fact_id=None,
                result_json="{}",
                recorded_at=now,
            )
            result: dict[str, Any]
            if data.operation == "ownership":
                old = db.scalar(
                    select(AssetAction)
                    .where(
                        AssetAction.user_id == actor.id,
                        AssetAction.asset_id == asset.id,
                        AssetAction.ownership_fact_id.is_not(None),
                    )
                    .order_by(AssetAction.recorded_at.desc())
                    .limit(1)
                )
                row.ownership_fact_id = self._fact(
                    db,
                    actor,
                    row,
                    "owned",
                    data.status == "owned",
                    when,
                    old.ownership_fact_id if old else None,
                )
                row.status_fact_id = self._fact(
                    db,
                    actor,
                    row,
                    "asset_status",
                    data.status or "owned",
                    when,
                    old.status_fact_id if old else None,
                )
                result = {
                    "operation": "ownership",
                    "status": data.status,
                    "source_id": source.id,
                }
            else:
                assert data.decision_id is not None
                decision = self.reconcile._decision(db, actor, data.decision_id)
                bound = db.scalar(
                    select(Binding).where(
                        Binding.user_id == actor.id,
                        Binding.decision_id == decision.id,
                        Binding.asset_id == asset.id,
                    )
                )
                observation = self.reconcile._observation(
                    db, actor, decision.observation_id
                )
                discovery = DiscoveryInput.model_validate_json(observation.payload)
                if not bound or decision.superseded_at is not None:
                    raise NoteConflict("This decision changed. Reload the item.")
                targets = [data.target_asset_id] if data.target_asset_id else None
                if discovery.quantity != 1:
                    if data.operation != "reassociate" or not data.target_asset_id:
                        raise MemoryError(
                            "Multi-unit corrections require an existing target item"
                        )
                    bindings = self.reconcile._bindings(db, actor, decision.id)
                    if len(bindings) != discovery.quantity or [
                        item.unit for item in bindings
                    ] != list(range(discovery.quantity)):
                        raise MemoryError("Incomplete unit mapping; reload the item")
                    targets = [
                        data.target_asset_id
                        if item.unit == bound.unit
                        else item.asset_id
                        for item in bindings
                    ]
                    if len(set(targets)) != discovery.quantity:
                        raise MemoryError(
                            "Each unit must remain a distinct physical item"
                        )
                if data.target_asset_id:
                    target = self.memory._entity(db, actor, data.target_asset_id)
                    if target.kind != "asset":
                        raise MemoryError("Target must be a physical item")
                changed = self.reconcile._change_in(
                    db,
                    actor,
                    observation.id,
                    decision.id,
                    "undo" if data.operation == "undo" else "resolve",
                    targets,
                    recorded_at=now,
                )
                if data.operation == "reassociate":
                    # Retain the actual new target as well as explicitly supplied
                    # targets, so the receiving record can inspect this correction.
                    row.target_asset_id = changed.asset_ids[bound.unit]
                result = {
                    "operation": data.operation,
                    "source_id": source.id,
                    "decision": changed.model_dump(mode="json"),
                }
                if discovery.quantity != 1:
                    result.update(unit=bound.unit + 1, quantity=discovery.quantity)
            row.result_json = json.dumps(result)
            db.add(row)
            db.flush()
            self.memory._index(
                db, actor, source.id, "source", asset.name + "\n" + source.text
            )
            self.memory._audit(db, actor, "asset_" + data.operation, row.id, now)
            return {"id": row.id, **result}

    def source_context(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.scalar(
                select(AssetAction)
                .where(
                    AssetAction.user_id == actor.id, AssetAction.source_id == source_id
                )
                .limit(1)
            )
            if row is None:
                return None
            asset = self.memory._entity(db, actor, row.asset_id)
            target = (
                self.memory._entity(db, actor, row.target_asset_id)
                if row.target_asset_id
                else None
            )
            result: dict[str, Any] = {
                "action_id": row.id,
                "asset_id": row.asset_id,
                "target_asset_id": row.target_asset_id,
                "asset_name": asset.name,
                "target_asset_name": target.name if target else None,
                "operation": row.operation,
                "user_selected_status": json.loads(row.result_json).get("status"),
            }
            if row.ownership_fact_id:
                fact = self.memory._assertion(db, actor, row.ownership_fact_id)
                result["ownership_statement_current_version"] = (
                    fact.superseded_at is None
                )
                result["ownership_valid_from"] = (
                    fact.valid_from.isoformat() if fact.valid_from else None
                )
                result["ownership_valid_to"] = (
                    fact.valid_to.isoformat() if fact.valid_to else None
                )
            recorded = json.loads(row.result_json)
            if row.operation in {"replacement", "replacement_withdrawn"}:
                fact = self.memory._assertion(db, actor, recorded["fact_id"])
                result["replacement_statement_current_version"] = (
                    fact.superseded_at is None
                )
                result["replacement_event_date"] = (
                    fact.valid_from.isoformat() if fact.valid_from else None
                )
            identifiers = []
            if "decision" in recorded:
                identifiers.append(recorded["decision"]["decision_id"])
            elif row.operation in {"batch_move", "batch_restore"}:
                key = (
                    "restored_decision_id"
                    if row.operation == "batch_restore"
                    else "moved_decision_id"
                )
                identifiers = [entry[key] for entry in recorded["entries"]]
            if identifiers:
                current = list(
                    db.scalars(
                        select(Decision.id)
                        .where(
                            Decision.user_id == actor.id,
                            Decision.id.in_(identifiers),
                            Decision.superseded_at.is_(None),
                        )
                        .limit(5)
                    )
                )
                result["association_versions_current"] = len(current)
                result["association_versions_total"] = len(identifiers)
            return result

    def related_sources(
        self, actor: Account, source_ids: list[str], entity_ids: list[str]
    ) -> list[str]:
        newer = aliased(AssetAction)
        with Session(self.engine) as db:
            return list(
                db.scalars(
                    select(AssetAction.source_id)
                    .join(
                        Entity,
                        or_(
                            Entity.id == AssetAction.asset_id,
                            Entity.id == AssetAction.target_asset_id,
                        ),
                    )
                    .where(
                        AssetAction.user_id == actor.id,
                        Entity.user_id == actor.id,
                        or_(
                            Entity.source_id.in_(source_ids), Entity.id.in_(entity_ids)
                        ),
                        ~exists(
                            select(newer.id).where(
                                newer.user_id == actor.id,
                                newer.asset_id == AssetAction.asset_id,
                                newer.target_asset_id.is_not_distinct_from(
                                    AssetAction.target_asset_id
                                ),
                                newer.operation == AssetAction.operation,
                                newer.recorded_at > AssetAction.recorded_at,
                            )
                        ),
                    )
                    .distinct()
                    .order_by(AssetAction.recorded_at.desc())
                    .limit(8)
                )
            )

    def export_page(
        self, actor: Account, cursor: str = "", limit: int = 25
    ) -> dict[str, Any]:
        if len(cursor) > 36 or not 1 <= limit <= 25:
            raise MemoryError("Invalid action export page")
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(AssetAction)
                    .where(AssetAction.user_id == actor.id, AssetAction.id > cursor)
                    .order_by(AssetAction.id)
                    .limit(limit + 1)
                )
            )
            return {
                "items": [
                    {
                        column.name: getattr(row, column.name)
                        for column in AssetAction.__table__.columns
                        if column.name != "user_id"
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }
