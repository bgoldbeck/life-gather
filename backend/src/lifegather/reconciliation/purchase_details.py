"""Human-entered, source-backed receipt claims; no floating point or AI writes."""

import re
from datetime import date
from typing import Any
from uuid import uuid4

from pydantic import Field
from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, fingerprint
from lifegather.reconciliation.receipt_models import ReceiptDetail, ReceiptProposal
from lifegather.reconciliation.receipts import (
    ReceiptChoice,
    ReceiptRead,
    ReceiptReview,
    ReceiptService,
)


class DetailRead(ReceiptRead):
    index: int = Field(ge=0, le=7)
    before_revision: int = Field(default=0, ge=0, le=2147483647)


class DetailSave(ReceiptRead):
    index: int = Field(ge=0, le=7)
    expected_head: str | None = Field(default=None, min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    line_total: str | None = Field(
        default=None, pattern=r"^(?:0|[1-9][0-9]{0,8})\.[0-9]{2}$"
    )
    money_quote: str | None = Field(default=None, min_length=1, max_length=500)
    purchase_date: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
    )
    date_quote: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)


class PurchaseDetails:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.receipts = ReceiptService(engine)

    def context(
        self, db: Session, actor: Account, receipt_id: str, index: int
    ) -> tuple[ReceiptProposal, ReceiptChoice]:
        receipt = self.receipts.owned(db, actor, receipt_id)
        if receipt.state != "accepted" or not receipt.reviewed_json:
            raise MemoryError("Confirm the receipt before recording purchase details")
        reviewed = ReceiptReview.model_validate_json(receipt.reviewed_json)
        choice = next((c for c in reviewed.choices if c.index == index), None)
        if (
            choice is None
            or choice.action == "skip"
            or choice.fields.kind != "purchase"
        ):
            raise MemoryError("Purchase details require a selected purchased item")
        return receipt, choice

    @staticmethod
    def query(actor: Account, identifier: str, index: int) -> Select[ReceiptDetail]:
        return select(ReceiptDetail).where(
            ReceiptDetail.user_id == actor.id,
            ReceiptDetail.receipt_id == identifier,
            ReceiptDetail.line_index == index,
        )

    @staticmethod
    def view(row: ReceiptDetail) -> dict[str, Any]:
        return {
            "id": row.id,
            "revision": row.revision,
            "source_id": row.source_id,
            "line_total": f"{row.total_minor // 100}.{row.total_minor % 100:02d}"
            if row.total_minor is not None
            else None,
            "total_minor": row.total_minor,
            "currency": row.currency,
            "money_quote": row.money_quote,
            "purchase_date": row.purchase_date,
            "date_quote": row.date_quote,
            "reason": row.reason,
            "recorded_at": row.recorded_at,
        }

    def get(self, actor: Account, value: DetailRead) -> dict[str, Any]:
        data = DetailRead.model_validate(value)
        with Session(self.engine) as db:
            receipt, choice = self.context(db, actor, data.receipt_id, data.index)
            query = self.query(actor, receipt.id, data.index)
            head = db.scalar(query.order_by(ReceiptDetail.revision.desc()).limit(1))
            if data.before_revision:
                query = query.where(ReceiptDetail.revision < data.before_revision)
            rows = list(
                db.scalars(query.order_by(ReceiptDetail.revision.desc()).limit(6))
            )
            available = True
            try:
                self.receipts.source(db, actor, receipt.source_id)
            except MemoryError:
                available = False
            return {
                "receipt_id": receipt.id,
                "index": data.index,
                "source_id": receipt.source_id,
                "quantity": choice.fields.quantity,
                "current_head": head.id if head else None,
                "current": self.view(head) if head else None,
                "can_edit": available,
                "items": [self.view(r) for r in rows[:5]],
                "next_revision": rows[4].revision if len(rows) > 5 else None,
            }

    def save(self, actor: Account, value: DetailSave) -> dict[str, Any]:
        data = DetailSave.model_validate(value)
        signature = fingerprint(data.model_dump())
        with self.receipts.memory._write() as db:
            receipt, choice = self.context(db, actor, data.receipt_id, data.index)
            used = db.scalar(
                select(ReceiptDetail).where(
                    ReceiptDetail.user_id == actor.id,
                    ReceiptDetail.request_id == data.request_id,
                )
            )
            if used:
                if used.fingerprint != signature:
                    raise NoteConflict("Purchase detail request conflict")
                return self.view(used)
            self.receipts.source(db, actor, receipt.source_id)
            head = db.scalar(
                self.query(actor, receipt.id, data.index)
                .order_by(ReceiptDetail.revision.desc())
                .limit(1)
            )
            if (head.id if head else None) != data.expected_head:
                raise NoteConflict("Purchase details changed; reload before correcting")
            if not data.reason.strip():
                raise MemoryError("Explain this purchase detail revision")
            text = self.receipts.source(db, actor, receipt.source_id)
            total = None
            if data.line_total is None:
                if data.money_quote is not None:
                    raise MemoryError("A money quote requires a line total")
            else:
                quote = data.money_quote or ""
                if not quote or quote not in text or choice.fields.quote not in quote:
                    raise MemoryError(
                        "Quote the item and its line total exactly from the source"
                    )
                amounts = re.findall(
                    r"\bline total\s*:?\s*USD ([0-9]+\.[0-9]{2})(?![0-9.])", quote, re.I
                )
                if amounts != [data.line_total]:
                    raise MemoryError(
                        "Use one Line total: USD 0.00 passage; "
                        "dollar symbols are ambiguous"
                    )
                whole, fraction = data.line_total.split(".")
                total = int(whole) * 100 + int(fraction)
            if data.purchase_date is None:
                if data.date_quote is not None:
                    raise MemoryError("A date quote requires a purchase date")
            else:
                try:
                    date.fromisoformat(data.purchase_date)
                except ValueError:
                    raise MemoryError(
                        "Purchase date must be a real YYYY-MM-DD date"
                    ) from None
                quote = data.date_quote or ""
                dates = re.findall(
                    r"\bpurchase date\s*:?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})(?![0-9])",
                    quote,
                    re.I,
                )
                if not quote or quote not in text or dates != [data.purchase_date]:
                    raise MemoryError("Use an exact Purchase date: YYYY-MM-DD passage")
            if head is None and total is None and data.purchase_date is None:
                raise MemoryError("Add a sourced total or purchase date first")
            row = ReceiptDetail(
                id=str(uuid4()),
                user_id=actor.id,
                receipt_id=receipt.id,
                source_id=receipt.source_id,
                line_index=data.index,
                revision=head.revision + 1 if head else 1,
                total_minor=total,
                currency="USD" if total is not None else None,
                money_quote=data.money_quote,
                purchase_date=data.purchase_date,
                date_quote=data.date_quote,
                reason=data.reason,
                request_id=data.request_id,
                fingerprint=signature,
                recorded_at=self.receipts.memory.clock(),
            )
            db.add(row)
            db.flush()
            self.receipts.memory._audit(
                db, actor, "receipt_details_recorded", row.id, row.recorded_at
            )
            return self.view(row)
