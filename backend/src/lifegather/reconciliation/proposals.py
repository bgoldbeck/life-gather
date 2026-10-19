"""Private extraction candidates; only explicit deterministic review writes assets."""

import json
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Entity
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.origins import change_origin
from lifegather.memory.service import (
    MemoryError,
    MemoryService,
    fingerprint,
    normalized,
)
from lifegather.reconciliation.models import Binding, Decision, Observation
from lifegather.reconciliation.proposal_models import AssetProposal
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


class AssetFields(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(min_length=1, max_length=100)
    model: str | None = Field(min_length=1, max_length=100)
    serial: str | None = Field(min_length=1, max_length=100)
    kind: Literal["purchase", "possession", "mention"]
    quote: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def supported_shape(self) -> Self:
        if any(
            value is not None and not value.strip()
            for value in (
                self.name,
                self.manufacturer,
                self.model,
                self.serial,
                self.quote,
            )
        ):
            raise ValueError("Item details cannot be blank")
        if (self.model or self.serial) and not self.manufacturer:
            raise ValueError("Model and serial need manufacturer context")
        return self


class AssetExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidate: AssetFields | None
    explanation: str = Field(min_length=1, max_length=500)


class ProposalRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    proposal_id: str = Field(min_length=1, max_length=36)


class ProposalPreview(ProposalRead):
    fields: AssetFields


class ProposalReview(ProposalRead):
    request_id: str = Field(min_length=1, max_length=100)
    action: Literal["new", "link", "reject", "auto"]
    fields: AssetFields | None = None
    asset_id: str | None = Field(default=None, min_length=1, max_length=36)
    candidate_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid_action(self) -> Self:
        if self.action != "reject" and self.fields is None:
            raise ValueError("Review the proposed fields before accepting")
        if (self.action == "link") != (self.asset_id is not None):
            raise ValueError("Choose an existing item only when linking")
        if self.action == "reject" and self.fields is not None:
            raise ValueError("Reject does not edit fields")
        return self


class ProposalService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.reconcile = ReconciliationService(engine)

    @staticmethod
    def _owned(db: Session, actor: Account, identifier: str) -> AssetProposal:
        row = db.scalar(
            select(AssetProposal).where(
                AssetProposal.user_id == actor.id, AssetProposal.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Asset proposal not found")
        return row

    def _source(self, db: Session, actor: Account, identifier: str) -> str:
        source = self.memory._source(db, actor, identifier)
        if not NoteService.is_note(source):
            raise MemoryError("Choose a saved text note")
        root = NoteService._root(db, actor, source)
        if NoteService._head(db, actor, root) != source.id:
            raise NoteConflict("This note has changed. Open the current note first.")
        from lifegather.photos.models import Photo

        photo = db.scalar(
            select(Photo).where(Photo.user_id == actor.id, Photo.source_id == root)
        )
        if photo and photo.deleted_at is not None:
            raise MemoryError(
                "The original photo was deleted; this proposal cannot be accepted"
            )
        from lifegather.documents.models import Document

        document = db.scalar(
            select(Document).where(
                Document.user_id == actor.id, Document.source_id == root
            )
        )
        if document and document.deleted_at is not None:
            raise MemoryError(
                "The original PDF was deleted; this proposal cannot be accepted"
            )
        return source.text

    @staticmethod
    def discovery(source_id: str, fields: AssetFields) -> DiscoveryInput:
        return DiscoveryInput(
            source_id=source_id,
            item_key="asset-proposal",
            quantity=1,
            **fields.model_dump(),
        )

    def _validate(
        self, db: Session, actor: Account, source_id: str, fields: AssetFields
    ) -> DiscoveryInput:
        text = self._source(db, actor, source_id)
        data = self.discovery(source_id, AssetFields.model_validate(fields))
        if data.quote not in text:
            raise MemoryError("Supporting quote must appear exactly in the saved note")
        if data.serial and data.serial not in data.quote:
            raise MemoryError("Serial identifiers must match the source exactly")
        if any(
            value and normalized(value) not in normalized(data.quote)
            for value in (data.name, data.manufacturer, data.model, data.serial)
        ):
            raise MemoryError("Item details must appear in the supporting quote")
        return data

    def existing(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            self._source(db, actor, source_id)
            row = db.scalar(
                select(AssetProposal).where(
                    AssetProposal.user_id == actor.id,
                    AssetProposal.source_id == source_id,
                )
            )
            return self._view(db, actor, row) if row else None

    def create(
        self, actor: Account, source_id: str, value: AssetExtraction
    ) -> dict[str, Any]:
        with self.memory._write() as db:
            return self._create_in(db, actor, source_id, value)

    def _create_in(
        self, db: Session, actor: Account, source_id: str, value: AssetExtraction
    ) -> dict[str, Any]:
        data = AssetExtraction.model_validate(value)
        self._source(db, actor, source_id)
        existing = db.scalar(
            select(AssetProposal).where(
                AssetProposal.user_id == actor.id,
                AssetProposal.source_id == source_id,
            )
        )
        if existing:
            return self._view(db, actor, existing)
        from lifegather.reconciliation.receipts import active_receipt

        active_receipt(db, actor, source_id)
        if data.candidate:
            self._validate(db, actor, source_id, data.candidate)
        now = self.memory.clock()
        row = AssetProposal(
            id=str(uuid4()),
            user_id=actor.id,
            source_id=source_id,
            recorded_at=now,
            state="proposed" if data.candidate else "no_item",
            proposed_json=data.model_dump_json(),
            reviewed_json=None,
            observation_id=None,
            request_id=None,
            fingerprint=None,
            result_json="{}",
            reviewed_at=None,
        )
        db.add(row)
        db.flush()
        self.memory._audit(db, actor, "asset_proposed", row.id, now)
        return self._view(db, actor, row)

    def _matching_observation(
        self, db: Session, actor: Account, data: DiscoveryInput
    ) -> Observation:
        product = (
            db.scalar(
                select(Entity.id).where(
                    Entity.user_id == actor.id,
                    Entity.operation_key
                    == "reconcile:product:"
                    + fingerprint(
                        [normalized(data.manufacturer), normalized(data.model)]
                    ),
                )
            )
            if data.manufacturer and data.model
            else None
        )
        return Observation(
            product_id=product,
            serial_key=fingerprint(
                [normalized(data.manufacturer or ""), data.serial.strip()]
            )
            if data.serial
            else None,
            line_id=None,
        )

    def _matches(
        self, db: Session, actor: Account, data: DiscoveryInput
    ) -> tuple[list[str], list[str]]:
        observation = self._matching_observation(db, actor, data)
        outcome, _, targets, candidates = self.reconcile.matcher._choose(
            db, actor, observation, data, False
        )
        # Keep historical serial bindings in identity checks after undo/rejection.
        serial_targets = (
            list(
                db.scalars(
                    select(Binding.asset_id)
                    .join(Decision, Decision.id == Binding.decision_id)
                    .join(Observation, Observation.id == Decision.observation_id)
                    .where(
                        Binding.user_id == actor.id,
                        Observation.user_id == actor.id,
                        Observation.serial_key == observation.serial_key,
                    )
                    .distinct()
                    .limit(101)
                )
            )
            if observation.serial_key
            else []
        )
        reliable = serial_targets or (targets if outcome == "enrich" else [])
        return sorted(set(targets + candidates + serial_targets))[:100], reliable

    def _view(self, db: Session, actor: Account, row: AssetProposal) -> dict[str, Any]:
        proposed = AssetExtraction.model_validate_json(row.proposed_json)
        source = self.memory._source(db, actor, row.source_id)
        head = NoteService._head(db, actor, NoteService._root(db, actor, source))
        matches: list[str] = []
        if proposed.candidate and row.state == "proposed":
            matches, _ = self._matches(
                db, actor, self.discovery(row.source_id, proposed.candidate)
            )
        from lifegather.photos.models import Photo

        photo = db.scalar(
            select(Photo).where(
                Photo.user_id == actor.id,
                Photo.source_id == NoteService._root(db, actor, source),
            )
        )
        return {
            "photo": {"id": photo.id, "deleted_at": photo.deleted_at}
            if photo
            else None,
            "id": row.id,
            "source_id": row.source_id,
            "source_text": source.text,
            "current_source_id": head,
            "stale": head != source.id,
            "state": row.state,
            "proposed": proposed.model_dump(),
            "reviewed": json.loads(row.reviewed_json) if row.reviewed_json else None,
            "recorded_at": row.recorded_at,
            "reviewed_at": row.reviewed_at,
            "result": json.loads(row.result_json),
            "candidates": [
                {
                    "id": identifier,
                    "name": self.memory._entity(db, actor, identifier).name,
                }
                for identifier in matches
            ],
        }

    def get(self, actor: Account, proposal_id: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self._view(db, actor, self._owned(db, actor, proposal_id))

    def preview(self, actor: Account, value: ProposalPreview) -> dict[str, Any]:
        data = ProposalPreview.model_validate(value)
        with Session(self.engine) as db:
            row = self._owned(db, actor, data.proposal_id)
            if row.state != "proposed":
                raise NoteConflict("This proposal has already been reviewed")
            discovery = self._validate(db, actor, row.source_id, data.fields)
            candidates, reliable = self._matches(db, actor, discovery)
            return {
                "candidates": [
                    {"id": i, "name": self.memory._entity(db, actor, i).name}
                    for i in candidates
                ],
                "reliable_ids": reliable,
            }

    def for_source(self, actor: Account, source_id: str) -> str | None:
        with Session(self.engine) as db:
            self.memory._source(db, actor, source_id)
            return db.scalar(
                select(AssetProposal.id).where(
                    AssetProposal.user_id == actor.id,
                    AssetProposal.source_id == source_id,
                )
            )

    def review(self, actor: Account, value: ProposalReview) -> dict[str, Any]:
        data = ProposalReview.model_validate(value)
        signature = fingerprint(data.model_dump())
        with (
            self.memory._write() as db,
            change_origin(method="review", related_id=data.proposal_id),
        ):
            row = self._owned(db, actor, data.proposal_id)
            used = db.scalar(
                select(AssetProposal.id).where(
                    AssetProposal.user_id == actor.id,
                    AssetProposal.request_id == data.request_id,
                )
            )
            if used is not None and used != row.id:
                raise NoteConflict("Review request belongs to another proposal")
            if row.request_id == data.request_id:
                if row.fingerprint != signature:
                    raise NoteConflict("Review request conflict")
                return self._view(db, actor, row)
            if row.state != "proposed":
                raise NoteConflict("This proposal has already been reviewed")
            if data.action == "reject":
                row.state = "rejected"
            else:
                from lifegather.reconciliation.receipts import active_receipt

                active_receipt(db, actor, row.source_id)
                assert data.fields is not None
                discovery = self._validate(db, actor, row.source_id, data.fields)
                if discovery.kind == "mention":
                    raise MemoryError(
                        "A mention does not establish possession or purchase"
                    )
                candidates, reliable = self._matches(db, actor, discovery)
                if data.action != "auto" and sorted(data.candidate_ids) != candidates:
                    raise NoteConflict(
                        "Possible duplicates changed. Check the details again."
                    )
                action = data.action
                asset_id = data.asset_id
                automatic_outcome = None
                if action == "auto":
                    automatic_outcome, reason, targets, _ = (
                        self.reconcile.matcher._choose(
                            db,
                            actor,
                            self._matching_observation(db, actor, discovery),
                            discovery,
                            False,
                        )
                    )
                    if automatic_outcome not in {"create", "enrich"} or (
                        automatic_outcome == "enrich"
                        and (len(targets) != 1 or len(reliable) != 1)
                    ):
                        if len(reliable) > 1:
                            reason = (
                                "Identifier history is ambiguous; choose explicitly"
                            )
                        return {
                            **self._view(db, actor, row),
                            "automatic_outcome": "review",
                            "automatic_reason": reason,
                            "automatic_check": {
                                "candidates": [
                                    {
                                        "id": identifier,
                                        "name": self.memory._entity(
                                            db, actor, identifier
                                        ).name,
                                    }
                                    for identifier in candidates
                                ],
                                "reliable_ids": reliable,
                            },
                        }
                    action = "link" if automatic_outcome == "enrich" else "new"
                    asset_id = targets[0] if action == "link" else None
                if action == "new" and reliable:
                    raise NoteConflict(
                        "An existing item matches this identifier; review the same item"
                    )
                if action == "link" and asset_id not in candidates:
                    raise NoteConflict(
                        "Selected item is no longer a candidate; reload the proposal"
                    )
                result = self.reconcile._discover_in(db, actor, discovery)
                if automatic_outcome and result.outcome != automatic_outcome:
                    raise NoteConflict(
                        "Existing discovery history needs explicit review"
                    )
                if action == "link":
                    result = self.reconcile._change_in(
                        db,
                        actor,
                        result.id,
                        result.decision_id,
                        "resolve",
                        [asset_id] if asset_id else None,
                    )
                elif result.outcome == "review":
                    result = self.reconcile._change_in(
                        db, actor, result.id, result.decision_id, "resolve", None
                    )
                from lifegather.photos.models import Photo
                from lifegather.photos.service import PhotoService

                source = self.memory._source(db, actor, row.source_id)
                root = NoteService._root(db, actor, source)
                photo = db.scalar(
                    select(Photo).where(
                        Photo.user_id == actor.id, Photo.source_id == root
                    )
                )
                if photo:
                    photos = PhotoService(self.engine)
                    for asset_id in result.asset_ids:
                        photos.attach(db, actor, photo, asset_id)
                    photo.updated_at = max(self.memory.clock(), photo.updated_at + 1)
                row.state = "accepted"
                row.reviewed_json = data.fields.model_dump_json()
                row.observation_id = result.id
                result_data = result.model_dump(mode="json")
                if automatic_outcome:
                    result_data["automatic_outcome"] = automatic_outcome
                row.result_json = json.dumps(result_data)
            row.request_id = data.request_id
            row.fingerprint = signature
            row.reviewed_at = self.memory.clock()
            self.memory._audit(
                db, actor, "asset_proposal_" + row.state, row.id, row.reviewed_at
            )
            db.flush()
            return self._view(db, actor, row)

    def export_page(
        self, actor: Account, cursor: str = "", limit: int = 25
    ) -> dict[str, Any]:
        if len(cursor) > 36 or not 1 <= limit <= 25:
            raise MemoryError("Invalid proposal export page")
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(AssetProposal)
                    .where(AssetProposal.user_id == actor.id, AssetProposal.id > cursor)
                    .order_by(AssetProposal.id)
                    .limit(limit + 1)
                )
            )
            return {
                "items": [
                    {
                        column.name: getattr(row, column.name)
                        for column in AssetProposal.__table__.columns
                        if column.name != "user_id"
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }
