"""Sourced replacement relationships between distinct, existing physical items."""

import json
from datetime import UTC, date, datetime
from typing import Any, Self
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy import select

from lifegather.assets.actions import ActionService
from lifegather.assets.identity import canonical_id
from lifegather.assets.models import AssetAction
from lifegather.auth.store import Account
from lifegather.memory.models import Assertion
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import FactInput, Input, SourceInput
from lifegather.memory.service import MemoryError, fingerprint


class ReplacementRecord(Input):
    asset_id: str = Field(min_length=1, max_length=36)
    target_asset_id: str = Field(min_length=1, max_length=36)
    expected_action_id: str = Field(default="", max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)
    event_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.asset_id == self.target_asset_id:
            raise ValueError("A replacement must be a distinct physical item")
        if not self.note.strip():
            raise ValueError("Explain the replacement")
        if (
            self.event_date
            and date.fromisoformat(self.event_date) > datetime.now(UTC).date()
        ):
            raise ValueError("Future replacement events are not supported")
        return self


class ReplacementWithdraw(Input):
    action_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def explained(self) -> Self:
        if not self.note.strip():
            raise ValueError("Explain the withdrawal")
        return self


class ReplacementService(ActionService):
    def change(
        self, actor: Account, value: ReplacementRecord | ReplacementWithdraw
    ) -> dict[str, Any]:
        if isinstance(value, ReplacementRecord):
            data: ReplacementRecord | ReplacementWithdraw = (
                ReplacementRecord.model_validate(value)
            )
            operation = "replacement"
        else:
            data = ReplacementWithdraw.model_validate(value)
            operation = "replacement_withdrawn"
        signature = fingerprint({"operation": operation, **data.model_dump()})
        with self.memory._write() as db:
            replay = db.scalar(
                select(AssetAction).where(
                    AssetAction.user_id == actor.id,
                    AssetAction.request_id == data.request_id,
                )
            )
            if replay:
                if replay.fingerprint != signature:
                    raise NoteConflict("Action request conflict")
                return {"id": replay.id, **json.loads(replay.result_json)}
            if isinstance(data, ReplacementRecord):
                asset = self.memory._entity(db, actor, data.asset_id)
                target = self.memory._entity(db, actor, data.target_asset_id)
                if asset.kind != "asset" or target.kind != "asset":
                    raise MemoryError("Choose two existing physical items")
                if canonical_id(db, actor, asset.id) == canonical_id(
                    db, actor, target.id
                ):
                    raise MemoryError("A replacement must be a distinct physical item")
                previous = self.latest(db, actor, asset.id)
                if (previous.id if previous else "") != data.expected_action_id:
                    raise NoteConflict(
                        "This item changed. Reload before recording a replacement."
                    )
                duplicate = db.scalar(
                    select(Assertion.id)
                    .where(
                        Assertion.user_id == actor.id,
                        Assertion.subject_id == asset.id,
                        Assertion.predicate == "replaced_by",
                        Assertion.object_id == target.id,
                        Assertion.superseded_at.is_(None),
                    )
                    .limit(1)
                )
                if duplicate:
                    raise NoteConflict(
                        "This replacement relationship is already recorded"
                    )
                when = date.fromisoformat(data.event_date) if data.event_date else None
                now = max(
                    self.memory.clock(),
                    previous.recorded_at + 1 if previous else asset.recorded_at,
                )
                original = None
            else:
                original = db.scalar(
                    select(AssetAction).where(
                        AssetAction.user_id == actor.id,
                        AssetAction.id == data.action_id,
                        AssetAction.operation == "replacement",
                    )
                )
                if original is None or not original.target_asset_id:
                    raise MemoryError("Replacement action not found")
                asset = self.memory._entity(db, actor, original.asset_id)
                target = self.memory._entity(db, actor, original.target_asset_id)
                previous = self.latest(db, actor, asset.id)
                if previous is None or previous.id != original.id:
                    raise NoteConflict(
                        "Later corrections exist. Inspect the item history first."
                    )
                fact = self.memory._assertion(
                    db, actor, json.loads(original.result_json)["fact_id"]
                )
                if fact.superseded_at is not None:
                    raise NoteConflict("This replacement relationship already changed")
                now = max(
                    self.memory.clock(), original.recorded_at + 1, fact.recorded_at + 1
                )
                when = None
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
            identifier = str(uuid4())
            if isinstance(data, ReplacementRecord):
                relation = self.memory._put_fact_in(
                    db,
                    actor,
                    FactInput(
                        subject_id=asset.id,
                        predicate="replaced_by",
                        object_id=target.id,
                        status="stated",
                        source_id=source.id,
                        quote=source.text,
                        valid_from=when,
                        operation_key="asset-replacement:" + identifier,
                    ),
                    None,
                    recorded_at=now,
                )
                fact_id = relation.id
            else:
                fact.superseded_at = now
                fact_id = fact.id
            result = {
                "operation": operation,
                "source_id": source.id,
                "fact_id": fact_id,
                "asset_id": asset.id,
                "target_asset_id": target.id,
                "event_date": when.isoformat() if when else None,
                "replacement_action_id": original.id if original else identifier,
            }
            row = AssetAction(
                id=identifier,
                user_id=actor.id,
                asset_id=asset.id,
                target_asset_id=target.id,
                previous_id=previous.id if previous else None,
                source_id=source.id,
                request_id=data.request_id,
                fingerprint=signature,
                operation=operation,
                ownership_fact_id=None,
                status_fact_id=None,
                result_json=json.dumps(result),
                recorded_at=now,
            )
            db.add(row)
            db.flush()
            self.memory._index(
                db,
                actor,
                source.id,
                "source",
                asset.name + "\n" + target.name + "\n" + source.text,
            )
            self.memory._audit(db, actor, "asset_" + operation, row.id, now)
            return {"id": row.id, **result}
