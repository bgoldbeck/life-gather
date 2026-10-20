"""Explicit reversible physical identity choices, preserving original evidence."""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import Engine, delete, func, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.comparison import RecordComparison, RecordComparisonService
from lifegather.assets.identity import identity_group
from lifegather.assets.models import (
    AssetAction,
    AssetConsolidation,
    ConsolidationMember,
)
from lifegather.auth.store import Account
from lifegather.memory.models import Assertion
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import (
    MemoryError,
    MemoryService,
    fingerprint,
    normalized,
)
from lifegather.reconciliation.models import Decision


class ConsolidationPair(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    primary_id: str = Field(min_length=1, max_length=36)
    secondary_id: str = Field(min_length=1, max_length=36)

    @model_validator(mode="after")
    def distinct(self) -> "ConsolidationPair":
        if self.primary_id == self.secondary_id:
            raise ValueError("Choose two distinct records")
        return self


class Consolidate(ConsolidationPair):
    preview_token: str = Field(min_length=64, max_length=64)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)
    same_item_confirmed: StrictBool

    @model_validator(mode="after")
    def explicit(self) -> "Consolidate":
        if not self.same_item_confirmed or not self.note.strip():
            raise ValueError("Confirm the same physical item and explain the choice")
        return self


class ReverseConsolidation(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    consolidation_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class ConsolidationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.comparison = RecordComparisonService(engine)

    def _state(
        self, db: Session, actor: Account, primary: str, secondary: str
    ) -> tuple[dict[str, Any], str]:
        result = self.comparison._get_in(
            db, actor, RecordComparison(asset_id=primary, target_asset_id=secondary)
        )
        if not result["complete"]:
            raise MemoryError(
                "Complete record preview exceeds the consolidation limits"
            )
        identifiers = [primary, secondary]
        # Current comparison plus immutable revision IDs catches corrections that
        # later restore the same literal, and actions without current fact effects.
        facts = list(
            db.execute(
                select(Assertion.id, Assertion.recorded_at, Assertion.superseded_at)
                .where(
                    Assertion.user_id == actor.id,
                    or_(
                        Assertion.subject_id.in_(identifiers),
                        Assertion.object_id.in_(identifiers),
                    ),
                )
                .order_by(Assertion.id)
                .limit(501)
            )
        )
        actions = list(
            db.execute(
                select(AssetAction.id)
                .where(
                    AssetAction.user_id == actor.id,
                    or_(
                        AssetAction.asset_id.in_(identifiers),
                        AssetAction.target_asset_id.in_(identifiers),
                    ),
                )
                .order_by(AssetAction.id)
                .limit(501)
            )
        )
        choices = list(
            db.execute(
                select(
                    AssetConsolidation.id,
                    AssetConsolidation.primary_id,
                    AssetConsolidation.secondary_id,
                    AssetConsolidation.source_id,
                    AssetConsolidation.recorded_at,
                    AssetConsolidation.superseded_at,
                    AssetConsolidation.reverse_source_id,
                )
                .where(
                    AssetConsolidation.user_id == actor.id,
                    or_(
                        AssetConsolidation.primary_id.in_(identifiers),
                        AssetConsolidation.secondary_id.in_(identifiers),
                    ),
                )
                .order_by(AssetConsolidation.id)
                .limit(501)
            )
        )
        if len(facts) > 500 or len(actions) > 500 or len(choices) > 500:
            raise MemoryError("Record history exceeds the consolidation limits")
        return result, fingerprint(
            [
                result,
                [list(row) for row in facts],
                [list(row) for row in actions],
                [list(row) for row in choices],
            ]
        )

    def _preview(
        self, db: Session, actor: Account, primary: str, secondary: str
    ) -> dict[str, Any]:
        ConsolidationPair(primary_id=primary, secondary_id=secondary)
        # Validate both owners before consulting identity membership.
        for identifier in (primary, secondary):
            self.memory._entity(db, actor, identifier)
            if identity_group(db, actor, identifier):
                raise MemoryError(
                    "A selected record already belongs to a consolidation"
                )
        result, token = self._state(db, actor, primary, secondary)
        blocked = {"distinct_units", "replacement"}
        if any(warning["code"] in blocked for warning in result["warnings"]):
            raise MemoryError(
                "Distinct physical units or replacement items cannot consolidate"
            )
        for field in ("manufacturer", "serial", "vin"):
            values = {
                str(fact["value"]).strip()
                for fact in result["sections"]["statements"]
                if fact["subject_id"] in {primary, secondary}
                and fact["predicate"] == "profile_" + field
                and fact["value"] is not None
                and fact["status"] != "unknown"
            }
            if field == "serial":
                values.update(
                    entry["serial"].strip()
                    for entry in result["sections"]["associations"]
                    if entry["serial"]
                )
            if field == "manufacturer":
                values.update(
                    entry["manufacturer"].strip()
                    for entry in result["sections"]["associations"]
                    if entry["manufacturer"]
                )
                values = {normalized(value) for value in values}
            if len(values) > 1:
                raise MemoryError(
                    "Conflicting identifiers require correction before consolidation"
                )
        return {
            "comparison": result,
            "preview_token": token,
            "primary_id": primary,
            "secondary_id": secondary,
        }

    def preview(self, actor: Account, primary: str, secondary: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            return self._preview(db, actor, primary, secondary)

    @staticmethod
    def _result(row: AssetConsolidation, *, reversed: bool = False) -> dict[str, Any]:
        # Replay describes the original operation, even if it is now historical.
        return {
            "id": row.id,
            "primary_id": row.primary_id,
            "secondary_id": row.secondary_id,
            "source_id": row.reverse_source_id if reversed else row.source_id,
            "recorded_at": row.superseded_at if reversed else row.recorded_at,
            "operation": "reverse" if reversed else "consolidate",
        }

    def apply(self, actor: Account, value: Consolidate) -> dict[str, Any]:
        data = Consolidate.model_validate(value)
        signature = fingerprint(data.model_dump())
        with self.memory._write() as db, change_origin(method="correction"):
            previous = db.scalar(
                select(AssetConsolidation).where(
                    AssetConsolidation.user_id == actor.id,
                    AssetConsolidation.request_id == data.request_id,
                )
            )
            if previous:
                if previous.fingerprint != signature:
                    raise NoteConflict("Consolidation request conflict")
                return self._result(previous)
            preview = self._preview(db, actor, data.primary_id, data.secondary_id)
            if preview["preview_token"] != data.preview_token:
                raise NoteConflict("Records changed. Preview consolidation again.")
            now = max(
                self.memory.clock(),
                *(
                    max(row.recorded_at, row.superseded_at or 0) + 1
                    for row in db.scalars(
                        select(AssetConsolidation)
                        .where(
                            AssetConsolidation.user_id == actor.id,
                            or_(
                                AssetConsolidation.primary_id.in_(
                                    [data.primary_id, data.secondary_id]
                                ),
                                AssetConsolidation.secondary_id.in_(
                                    [data.primary_id, data.secondary_id]
                                ),
                            ),
                        )
                        .limit(501)
                    )
                ),
                *(
                    record["recorded_at"] + 1
                    for record in preview["comparison"]["records"]
                ),
                *(
                    fact["recorded_at"] + 1
                    for fact in preview["comparison"]["sections"]["statements"]
                ),
                *(
                    task["recorded_at"] + 1
                    for task in preview["comparison"]["sections"].get("maintenance", [])
                ),
                (
                    db.scalar(
                        select(func.max(Decision.recorded_at)).where(
                            Decision.user_id == actor.id,
                            Decision.id.in_(
                                [
                                    entry["decision_id"]
                                    for entry in preview["comparison"]["sections"][
                                        "associations"
                                    ]
                                ]
                            ),
                        )
                    )
                    or 0
                )
                + 1,
                (
                    db.scalar(
                        select(func.max(AssetAction.recorded_at)).where(
                            AssetAction.user_id == actor.id,
                            or_(
                                AssetAction.asset_id.in_(
                                    [data.primary_id, data.secondary_id]
                                ),
                                AssetAction.target_asset_id.in_(
                                    [data.primary_id, data.secondary_id]
                                ),
                            ),
                        )
                    )
                    or 0
                )
                + 1,
            )
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.note,
                    namespace="asset-consolidation",
                    external_id=data.request_id,
                ),
                recorded_at=now,
            )
            row = AssetConsolidation(
                id=str(uuid4()),
                user_id=actor.id,
                primary_id=data.primary_id,
                secondary_id=data.secondary_id,
                source_id=source.id,
                request_id=data.request_id,
                fingerprint=signature,
                state_token="",
                recorded_at=now,
                superseded_at=None,
                reverse_source_id=None,
                reverse_request_id=None,
                reverse_fingerprint=None,
            )
            db.add(row)
            db.flush()
            for identifier in (row.primary_id, row.secondary_id):
                db.add(
                    ConsolidationMember(
                        user_id=actor.id, entity_id=identifier, consolidation_id=row.id
                    )
                )
            db.flush()
            row.state_token = self._state(db, actor, row.primary_id, row.secondary_id)[
                1
            ]
            self.memory._audit(db, actor, "asset_consolidated", row.id, now)
            return self._result(row)

    def reverse(self, actor: Account, value: ReverseConsolidation) -> dict[str, Any]:
        data = ReverseConsolidation.model_validate(value)
        if not data.note.strip():
            raise MemoryError("Explain the reversal")
        signature = fingerprint(data.model_dump())
        with self.memory._write() as db, change_origin(method="correction"):
            replay = db.scalar(
                select(AssetConsolidation).where(
                    AssetConsolidation.user_id == actor.id,
                    AssetConsolidation.reverse_request_id == data.request_id,
                )
            )
            if replay:
                if replay.reverse_fingerprint != signature:
                    raise NoteConflict("Reversal request conflict")
                return self._result(replay, reversed=True)
            row = db.scalar(
                select(AssetConsolidation).where(
                    AssetConsolidation.user_id == actor.id,
                    AssetConsolidation.id == data.consolidation_id,
                )
            )
            if row is None:
                raise MemoryError("Consolidation not found")
            if row.superseded_at is not None:
                raise NoteConflict("Consolidation already reversed")
            if (
                self._state(db, actor, row.primary_id, row.secondary_id)[1]
                != row.state_token
            ):
                raise NoteConflict(
                    "Records changed after consolidation. Inspect current history."
                )
            now = max(self.memory.clock(), row.recorded_at + 1)
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.note,
                    namespace="asset-consolidation-reversal",
                    external_id=data.request_id,
                ),
                recorded_at=now,
            )
            row.superseded_at = now
            row.reverse_source_id = source.id
            row.reverse_request_id = data.request_id
            row.reverse_fingerprint = signature
            db.execute(
                delete(ConsolidationMember).where(
                    ConsolidationMember.user_id == actor.id,
                    ConsolidationMember.consolidation_id == row.id,
                )
            )
            self.memory._audit(db, actor, "asset_consolidation_reversed", row.id, now)
            return self._result(row, reversed=True)
