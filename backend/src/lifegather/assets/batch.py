"""Explicit, atomic movement of discovery bindings; never whole-record merging."""

import json
from typing import Any
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.assets.actions import ActionService
from lifegather.assets.models import AssetAction
from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import Input, SourceInput
from lifegather.memory.service import MemoryError, fingerprint
from lifegather.reconciliation.models import Binding, Decision
from lifegather.reconciliation.schemas import DiscoveryInput


class EvidenceMovePreview(Input):
    asset_id: str = Field(min_length=1, max_length=36)
    target_asset_id: str = Field(min_length=1, max_length=36)

    @model_validator(mode="after")
    def distinct(self) -> "EvidenceMovePreview":
        if self.asset_id == self.target_asset_id:
            raise ValueError("Choose a different physical item")
        return self


class EvidenceMove(EvidenceMovePreview):
    preview_token: str = Field(min_length=64, max_length=64)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class EvidenceRestore(Input):
    action_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class EvidenceBatchService(ActionService):
    def _preview(
        self, db: Session, actor: Account, data: EvidenceMovePreview
    ) -> dict[str, Any]:
        source = self.memory._entity(db, actor, data.asset_id)
        target = self.memory._entity(db, actor, data.target_asset_id)
        if source.kind != "asset" or target.kind != "asset":
            raise MemoryError("Choose two physical items")
        rows = list(
            db.scalars(
                select(Decision)
                .join(Binding, Binding.decision_id == Decision.id)
                .where(
                    Decision.user_id == actor.id,
                    Binding.user_id == actor.id,
                    Binding.asset_id == source.id,
                    Decision.superseded_at.is_(None),
                )
                .order_by(Decision.id)
                .limit(6)
            )
        )
        if not rows or len(rows) > 5:
            raise MemoryError(
                "Move between one and five discovery associations at once"
            )
        entries = []
        for decision in rows:
            observation = self.reconcile._observation(
                db, actor, decision.observation_id
            )
            discovery = DiscoveryInput.model_validate_json(observation.payload)
            bindings = self.reconcile._bindings(db, actor, decision.id)
            original = [binding.asset_id for binding in bindings]
            if len(original) != discovery.quantity or [
                b.unit for b in bindings
            ] != list(range(discovery.quantity)):
                raise MemoryError("Incomplete unit mapping")
            if original.count(source.id) != 1 or target.id in original:
                raise MemoryError("Distinct receipt units cannot become the same item")
            entries.append(
                {
                    "decision_id": decision.id,
                    "observation_id": observation.id,
                    "source_id": observation.source_id,
                    "name": discovery.name,
                    "quote": discovery.quote[:400],
                    "quote_truncated": len(discovery.quote) > 400,
                    "unit": original.index(source.id) + 1,
                    "quantity": discovery.quantity,
                    "original_asset_ids": original,
                }
            )
        source_head = self.latest(db, actor, source.id)
        target_head = self.latest(db, actor, target.id)
        snapshot = {
            "asset_id": source.id,
            "target_asset_id": target.id,
            "source_head": source_head.id if source_head else "",
            "target_head": target_head.id if target_head else "",
            "entries": entries,
        }
        return {
            **snapshot,
            "asset_name": source.name,
            "target_asset_name": target.name,
            "preview_token": fingerprint(snapshot),
        }

    def preview(self, actor: Account, value: EvidenceMovePreview) -> dict[str, Any]:
        data = EvidenceMovePreview.model_validate(value)
        with Session(self.engine) as db:
            return self._preview(db, actor, data)

    def _replay(
        self, db: Session, actor: Account, request_id: str, signature: str
    ) -> dict[str, Any] | None:
        row = db.scalar(
            select(AssetAction).where(
                AssetAction.user_id == actor.id, AssetAction.request_id == request_id
            )
        )
        if row is None:
            return None
        if row.fingerprint != signature:
            raise NoteConflict("Action request conflict")
        return {"id": row.id, **json.loads(row.result_json)}

    def _save(
        self,
        db: Session,
        actor: Account,
        data: EvidenceMove | EvidenceRestore,
        snapshot: dict[str, Any],
        operation: str,
        signature: str,
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not data.note.strip():
            raise MemoryError("Explain the change")
        previous = self.latest(db, actor, snapshot["asset_id"])
        # Decisions advance their own logical clocks. A stalled/backward wall
        # clock must not place the explanation before any effect it describes.
        decision_key = (
            "restored_decision_id"
            if operation == "batch_restore"
            else "moved_decision_id"
        )
        decision_times = [
            self.reconcile._decision(db, actor, entry[decision_key]).recorded_at
            for entry in entries
        ]
        now = max(
            self.memory.clock(),
            previous.recorded_at + 1 if previous else 0,
            self.memory._entity(db, actor, snapshot["asset_id"]).recorded_at,
            self.memory._entity(db, actor, snapshot["target_asset_id"]).recorded_at,
            *decision_times,
        )
        source = self.memory._ingest_in(
            db,
            actor,
            SourceInput(
                text=data.note,
                source_type="conversation",
                namespace="asset-action",
                external_id=data.request_id,
            ),
            recorded_at=now,
        )
        result = {
            "operation": operation,
            "source_id": source.id,
            "asset_id": snapshot["asset_id"],
            "target_asset_id": snapshot["target_asset_id"],
            "target_head": snapshot["target_head"],
            "entries": entries,
        }
        row = AssetAction(
            id=str(uuid4()),
            user_id=actor.id,
            asset_id=snapshot["asset_id"],
            target_asset_id=snapshot["target_asset_id"],
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
        self.memory._index(db, actor, source.id, "source", source.text)
        self.memory._audit(db, actor, "asset_" + operation, row.id, now)
        return {"id": row.id, **result}

    def move(self, actor: Account, value: EvidenceMove) -> dict[str, Any]:
        data = EvidenceMove.model_validate(value)
        signature = fingerprint({"operation": "batch_move", **data.model_dump()})
        with self.memory._write() as db:
            replay = self._replay(db, actor, data.request_id, signature)
            if replay is not None:
                return replay
            snapshot = self._preview(
                db,
                actor,
                EvidenceMovePreview(
                    asset_id=data.asset_id, target_asset_id=data.target_asset_id
                ),
            )
            if snapshot["preview_token"] != data.preview_token:
                raise NoteConflict("Evidence changed. Preview the move again.")
            entries = []
            for entry in snapshot["entries"]:
                targets = [
                    data.target_asset_id if item == data.asset_id else item
                    for item in entry["original_asset_ids"]
                ]
                changed = self.reconcile._change_in(
                    db,
                    actor,
                    entry["observation_id"],
                    entry["decision_id"],
                    "resolve",
                    targets,
                )
                entries.append({**entry, "moved_decision_id": changed.decision_id})
            return self._save(
                db, actor, data, snapshot, "batch_move", signature, entries
            )

    def restore(self, actor: Account, value: EvidenceRestore) -> dict[str, Any]:
        data = EvidenceRestore.model_validate(value)
        signature = fingerprint({"operation": "batch_restore", **data.model_dump()})
        with self.memory._write() as db:
            replay = self._replay(db, actor, data.request_id, signature)
            if replay is not None:
                return replay
            row = db.scalar(
                select(AssetAction).where(
                    AssetAction.user_id == actor.id,
                    AssetAction.id == data.action_id,
                    AssetAction.operation == "batch_move",
                )
            )
            if row is None:
                raise MemoryError("Evidence move not found")
            latest = self.latest(db, actor, row.asset_id)
            snapshot = json.loads(row.result_json)
            target_head = self.latest(db, actor, snapshot["target_asset_id"])
            if (
                latest is None
                or latest.id != row.id
                or (target_head.id if target_head else "") != snapshot["target_head"]
            ):
                raise NoteConflict(
                    "An item changed after this move; inspect its history"
                )
            entries = []
            for entry in snapshot["entries"]:
                current = self.reconcile._decision(
                    db, actor, entry["moved_decision_id"]
                )
                if current.superseded_at is not None:
                    raise NoteConflict("Moved evidence changed; inspect its history")
                restored = self.reconcile._change_in(
                    db,
                    actor,
                    entry["observation_id"],
                    current.id,
                    "resolve",
                    entry["original_asset_ids"],
                )
                entries.append({**entry, "restored_decision_id": restored.decision_id})
            return self._save(
                db, actor, data, snapshot, "batch_restore", signature, entries
            )
