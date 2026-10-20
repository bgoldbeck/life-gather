"""Bounded receipt drafts. Human review commits selected lines atomically."""

import json
import re
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.documents.models import Document
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.origins import change_origin
from lifegather.memory.service import (
    MemoryError,
    MemoryService,
    fingerprint,
    normalized,
)
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoService
from lifegather.reconciliation.proposal_models import AssetProposal
from lifegather.reconciliation.proposals import AssetFields, ProposalService
from lifegather.reconciliation.receipt_models import ReceiptProposal
from lifegather.reconciliation.schemas import DiscoveryInput

QUANTITY = re.compile(
    r"\b(?:qty\.?|quantity|count)\s*[:=]?\s*(\d+)\b|\b(\d+)\s+(?:units?|pcs|pieces)\b",
    re.I,
)


class ReceiptFields(AssetFields):
    quote: str = Field(min_length=1, max_length=1000)
    quantity: int = Field(ge=1, le=20)
    quantity_quote: str | None = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def serial_unit(self) -> Self:
        if self.serial and self.quantity != 1:
            raise ValueError("A serial identifies one physical unit")
        return self


class ReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[ReceiptFields] = Field(max_length=8)
    explanation: str = Field(min_length=1, max_length=500)


class ReceiptRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    receipt_id: str = Field(min_length=1, max_length=36)


class ReceiptPreview(ReceiptRead):
    index: int = Field(ge=0, le=7)
    fields: ReceiptFields


class ReceiptChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    index: int = Field(ge=0, le=7)
    fields: ReceiptFields
    action: Literal["new", "link", "skip", "auto"]
    asset_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(
        default_factory=list, max_length=20
    )
    check: str = Field(default="", max_length=64)


class ReceiptReview(ReceiptRead):
    request_id: str = Field(min_length=1, max_length=100)
    reject: bool = False
    choices: list[ReceiptChoice] = Field(default_factory=list, max_length=8)


def active_single(db: Session, actor: Account, source_id: str) -> None:
    if (
        db.scalar(
            select(AssetProposal.id).where(
                AssetProposal.user_id == actor.id,
                AssetProposal.source_id == source_id,
                AssetProposal.state.in_(["proposed", "accepted"]),
            )
        )
        is not None
    ):
        raise NoteConflict("Review or reject the existing single-item proposal first")


def active_receipt(db: Session, actor: Account, source_id: str) -> None:
    if (
        db.scalar(
            select(ReceiptProposal.id).where(
                ReceiptProposal.user_id == actor.id,
                ReceiptProposal.source_id == source_id,
                ReceiptProposal.state.in_(["proposed", "accepted"]),
            )
        )
        is not None
    ):
        raise NoteConflict("Use the existing multi-item receipt review for this source")


class ReceiptService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.proposals = ProposalService(engine)
        self.reconcile = self.proposals.reconcile

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> ReceiptProposal:
        row = db.scalar(
            select(ReceiptProposal).where(
                ReceiptProposal.user_id == actor.id, ReceiptProposal.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Receipt proposal not found")
        return row

    def source(self, db: Session, actor: Account, identifier: str) -> str:
        value = self.proposals._source(db, actor, identifier)
        source = self.memory._source(db, actor, identifier)
        root = NoteService._root(db, actor, source)
        document = db.scalar(
            select(Document.id).where(
                Document.user_id == actor.id,
                Document.source_id == root,
                Document.deleted_at.is_not(None),
            )
        )
        if document is not None:
            raise MemoryError(
                "The original document was deleted; this receipt cannot be confirmed"
            )
        return value

    def validate(
        self,
        db: Session,
        actor: Account,
        source_id: str,
        value: ReceiptFields,
        index: int,
    ) -> DiscoveryInput:
        fields = ReceiptFields.model_validate(value)
        text = self.source(db, actor, source_id)
        basic = AssetFields.model_validate(
            fields.model_dump(exclude={"quantity", "quantity_quote"})
        )
        discovery = self.proposals._validate(db, actor, source_id, basic)
        quantities = {int(a or b) for a, b in QUANTITY.findall(fields.quote)}
        if not quantities and fields.quantity == 1:
            # A shortened quote must not hide an explicit multiple beside it.
            # Check repeated matches too; a first single-unit line cannot mask
            # the same ambiguous passage on a later multi-unit line.
            offset = 0
            contexts: set[tuple[int, int]] = set()
            for attempt in range(33):
                position = text.find(fields.quote, offset)
                if position < 0:
                    break
                if attempt == 32:
                    raise MemoryError(
                        "Quote is ambiguous; include the full item and quantity passage"
                    )
                end = position + len(fields.quote)
                left = text.rfind("\n", 0, position) + 1
                right = text.find("\n", end)
                if right < 0:
                    right = len(text)
                if (left, right) not in contexts:
                    contexts.add((left, right))
                    nearby = {
                        int(a or b) for a, b in QUANTITY.findall(text[left:right])
                    }
                    if nearby and nearby != {1}:
                        raise MemoryError(
                            "Include the explicit quantity in this item's exact quote"
                        )
                offset = end
        if fields.quantity_quote is not None:
            if fields.quantity_quote not in fields.quote:
                raise MemoryError(
                    "Quantity quote must be part of this item's exact quote"
                )
            supported = {
                int(a or b) for a, b in QUANTITY.findall(fields.quantity_quote)
            }
            if supported != {fields.quantity}:
                raise MemoryError(
                    "Quantity needs an exact Qty/quantity/count/units passage"
                )
        elif fields.quantity != 1:
            raise MemoryError("Multiple units need a supporting quantity quote")
        if quantities and quantities != {fields.quantity}:
            raise MemoryError("Item quote contains a conflicting quantity")
        if fields.quote not in text:
            raise MemoryError("Item quote must occur in the saved source")
        return DiscoveryInput.model_validate(
            {
                **discovery.model_dump(),
                "quantity": fields.quantity,
                "item_key": f"receipt-line-{index}",
            }
        )

    @staticmethod
    def bounded(items: list[ReceiptFields]) -> None:
        if sum(item.quantity for item in items) > 20:
            raise MemoryError("Review at most 20 physical units per receipt")
        if len({item.quote for item in items}) != len(items):
            raise MemoryError("Each receipt line needs a distinct supporting quote")
        serials = [
            (normalized(item.manufacturer or ""), item.serial)
            for item in items
            if item.serial
        ]
        if len(serials) != len(set(serials)):
            raise MemoryError("The same serial cannot identify two receipt lines")
        if (
            len(
                json.dumps([i.model_dump() for i in items], ensure_ascii=False).encode()
            )
            > 16000
        ):
            raise MemoryError(
                "Receipt details exceed the review limit; use shorter exact quotes"
            )

    def view(self, db: Session, actor: Account, row: ReceiptProposal) -> dict[str, Any]:
        value = ReceiptExtraction.model_validate_json(row.proposed_json)
        source = self.memory._source(db, actor, row.source_id)
        head = NoteService._head(db, actor, NoteService._root(db, actor, source))
        reviewed = (
            ReceiptReview.model_validate_json(row.reviewed_json)
            if row.reviewed_json
            else None
        )
        items = (
            [
                (
                    value.items[choice.index]
                    if choice.action == "skip"
                    else choice.fields
                ).model_dump()
                for choice in sorted(reviewed.choices, key=lambda c: c.index)
            ]
            if reviewed
            else value.model_dump()["items"]
        )
        return {
            "id": row.id,
            "source_id": source.id,
            "current_source_id": head,
            "stale": source.id != head,
            "state": row.state,
            "items": items,
            "explanation": value.explanation,
            "review_actions": [
                {"action": c.action, "asset_ids": c.asset_ids}
                for c in sorted(reviewed.choices, key=lambda c: c.index)
            ]
            if reviewed
            else None,
            "result": json.loads(row.result_json),
            "recorded_at": row.recorded_at,
        }

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self.view(db, actor, self.owned(db, actor, identifier))

    def for_source(self, actor: Account, source_id: str) -> str | None:
        with Session(self.engine) as db:
            self.memory._source(db, actor, source_id)
            return db.scalar(
                select(ReceiptProposal.id).where(
                    ReceiptProposal.user_id == actor.id,
                    ReceiptProposal.source_id == source_id,
                )
            )

    def existing(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            self.source(db, actor, source_id)
            row = db.scalar(
                select(ReceiptProposal).where(
                    ReceiptProposal.user_id == actor.id,
                    ReceiptProposal.source_id == source_id,
                )
            )
            return self.view(db, actor, row) if row else None

    def create(
        self, actor: Account, source_id: str, value: ReceiptExtraction
    ) -> dict[str, Any]:
        with self.memory._write() as db:
            return self._create_in(db, actor, source_id, value)

    def _create_in(
        self, db: Session, actor: Account, source_id: str, value: ReceiptExtraction
    ) -> dict[str, Any]:
        data = ReceiptExtraction.model_validate(value)
        self.bounded(data.items)
        self.source(db, actor, source_id)
        row = db.scalar(
            select(ReceiptProposal).where(
                ReceiptProposal.user_id == actor.id,
                ReceiptProposal.source_id == source_id,
            )
        )
        if row:
            return self.view(db, actor, row)
        active_single(db, actor, source_id)
        for index, item in enumerate(data.items):
            if item.kind != "mention":
                raise MemoryError(
                    "AI receipt suggestions must remain unverified mentions"
                )
            self.validate(db, actor, source_id, item, index)
        now = self.memory.clock()
        row = ReceiptProposal(
            id=str(uuid4()),
            user_id=actor.id,
            source_id=source_id,
            state="proposed" if data.items else "no_items",
            proposed_json=data.model_dump_json(),
            reviewed_json=None,
            result_json="{}",
            request_id=None,
            fingerprint=None,
            recorded_at=now,
            reviewed_at=None,
        )
        db.add(row)
        db.flush()
        self.memory._audit(db, actor, "receipt_proposed", row.id, now)
        return self.view(db, actor, row)

    def check(
        self,
        db: Session,
        actor: Account,
        row: ReceiptProposal,
        index: int,
        fields: ReceiptFields,
    ) -> dict[str, Any]:
        original = ReceiptExtraction.model_validate_json(row.proposed_json)
        if index >= len(original.items):
            raise MemoryError("Receipt line not found")
        discovery = self.validate(db, actor, row.source_id, fields, index)
        candidates, reliable = self.proposals._matches(db, actor, discovery)
        return {
            "candidates": [
                {"id": i, "name": self.memory._entity(db, actor, i).name}
                for i in candidates
            ],
            "reliable_ids": reliable,
            "check": fingerprint(
                [row.id, index, fields.model_dump(), candidates, reliable]
            ),
        }

    def preview(self, actor: Account, value: ReceiptPreview) -> dict[str, Any]:
        data = ReceiptPreview.model_validate(value)
        with Session(self.engine) as db:
            row = self.owned(db, actor, data.receipt_id)
            if row.state != "proposed":
                raise NoteConflict("Receipt was already reviewed")
            return self.check(db, actor, row, data.index, data.fields)

    def review(self, actor: Account, value: ReceiptReview) -> dict[str, Any]:
        data = ReceiptReview.model_validate(value)
        signature = fingerprint(data.model_dump())
        with (
            self.memory._write() as db,
            change_origin(method="review", related_id=data.receipt_id),
        ):
            row = self.owned(db, actor, data.receipt_id)
            used = db.scalar(
                select(ReceiptProposal.id).where(
                    ReceiptProposal.user_id == actor.id,
                    ReceiptProposal.request_id == data.request_id,
                )
            )
            if used and used != row.id:
                raise NoteConflict("Request belongs to another receipt")
            if row.request_id == data.request_id:
                if row.fingerprint != signature:
                    raise NoteConflict("Receipt review request conflict")
                return self.view(db, actor, row)
            if row.state != "proposed":
                raise NoteConflict("Receipt was already reviewed")
            original = ReceiptExtraction.model_validate_json(row.proposed_json)
            if data.reject:
                if data.choices:
                    raise MemoryError("Reject does not accept line changes")
                row.state = "rejected"
            else:
                active_single(db, actor, row.source_id)
                self.source(db, actor, row.source_id)
                if sorted(c.index for c in data.choices) != list(
                    range(len(original.items))
                ):
                    raise MemoryError(
                        "Review every receipt line once, including excluded lines"
                    )
                selected = [c for c in data.choices if c.action != "skip"]
                if not selected:
                    raise MemoryError("Select an item or reject the receipt")
                self.bounded([c.fields for c in selected])
                displayed = [
                    (
                        original.items[c.index] if c.action == "skip" else c.fields
                    ).model_dump()
                    for c in data.choices
                ]
                if len(json.dumps(displayed, ensure_ascii=False).encode()) > 16000:
                    raise MemoryError("Receipt details exceed the review limit")
                linked = [asset for c in selected for asset in c.asset_ids]
                if len(linked) != len(set(linked)):
                    raise MemoryError(
                        "A physical item cannot fill multiple receipt units"
                    )
                # Preflight every line before any derived graph write.
                automatic: dict[int, tuple[str, list[str]]] = {}
                automatic_checks = []
                needs_review = False
                for choice in selected:
                    if choice.fields.kind == "mention":
                        raise MemoryError(
                            "State purchase or possession before adding inventory"
                        )
                    checked = self.check(db, actor, row, choice.index, choice.fields)
                    if choice.action == "auto":
                        if choice.asset_ids:
                            raise MemoryError(
                                "Automatic identity does not accept targets"
                            )
                        discovery = self.validate(
                            db, actor, row.source_id, choice.fields, choice.index
                        )
                        outcome, reason, targets, _ = self.reconcile.matcher._choose(
                            db,
                            actor,
                            self.proposals._matching_observation(db, actor, discovery),
                            discovery,
                            False,
                        )
                        clear = outcome in {"create", "enrich"} and (
                            outcome != "enrich"
                            or (
                                len(targets) == choice.fields.quantity
                                and len(checked["reliable_ids"])
                                == choice.fields.quantity
                            )
                        )
                        automatic[choice.index] = (outcome, targets)
                        automatic_checks.append(
                            {
                                "index": choice.index,
                                **checked,
                                "reason": reason
                                if clear or outcome == "review"
                                else "Identifier history needs explicit review",
                                "outcome": outcome if clear else "review",
                            }
                        )
                        needs_review = needs_review or not clear
                        continue
                    if checked["check"] != choice.check:
                        raise NoteConflict(
                            "Item details or possible duplicates changed; check again"
                        )
                    candidates = {c["id"] for c in checked["candidates"]}
                    if choice.action == "new" and (
                        choice.asset_ids or checked["reliable_ids"]
                    ):
                        raise NoteConflict(
                            "An identifier matches an existing item; choose that item"
                        )
                    if choice.action == "link" and (
                        len(choice.asset_ids) != choice.fields.quantity
                        or len(set(choice.asset_ids)) != len(choice.asset_ids)
                        or not set(choice.asset_ids) <= candidates
                    ):
                        raise MemoryError(
                            "Choose a distinct existing item for each unit"
                        )
                if needs_review:
                    return {
                        **self.view(db, actor, row),
                        "automatic_outcome": "review",
                        "automatic_checks": automatic_checks,
                    }
                predicted = linked + [
                    target for _, targets in automatic.values() for target in targets
                ]
                if len(set(predicted)) != len(predicted):
                    raise MemoryError(
                        "A physical item cannot fill multiple receipt units"
                    )
                results = []
                for choice in selected:
                    discovery = self.validate(
                        db, actor, row.source_id, choice.fields, choice.index
                    )
                    result = self.reconcile._discover_in(db, actor, discovery)
                    if choice.action == "auto":
                        outcome, targets = automatic[choice.index]
                        if result.outcome != outcome or (
                            outcome == "enrich" and result.asset_ids != targets
                        ):
                            raise NoteConflict(
                                "Receipt lines affect each other's identity; "
                                "choose explicitly"
                            )
                    elif choice.action == "link":
                        result = self.reconcile._change_in(
                            db,
                            actor,
                            result.id,
                            result.decision_id,
                            "resolve",
                            choice.asset_ids,
                        )
                    elif result.outcome == "review":
                        result = self.reconcile._change_in(
                            db, actor, result.id, result.decision_id, "resolve", None
                        )
                    if choice.action == "new" and result.outcome == "enrich":
                        raise NoteConflict(
                            "A receipt identifier now matches an existing item"
                        )
                    root = NoteService._root(
                        db, actor, self.memory._source(db, actor, row.source_id)
                    )
                    photo = db.scalar(
                        select(Photo).where(
                            Photo.user_id == actor.id, Photo.source_id == root
                        )
                    )
                    if photo:
                        for asset in result.asset_ids:
                            PhotoService(self.engine).attach(db, actor, photo, asset)
                        photo.updated_at = max(
                            self.memory.clock(), photo.updated_at + 1
                        )
                    line = {"index": choice.index, **result.model_dump(mode="json")}
                    if choice.action == "auto":
                        line["automatic_outcome"] = result.outcome
                    results.append(line)
                row.state = "accepted"
                row.reviewed_json = data.model_dump_json()
                row.result_json = json.dumps({"lines": results})
            row.request_id = data.request_id
            row.fingerprint = signature
            row.reviewed_at = self.memory.clock()
            self.memory._audit(
                db, actor, "receipt_" + row.state, row.id, row.reviewed_at
            )
            db.flush()
            return self.view(db, actor, row)
