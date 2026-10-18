"""Human-entered, source-backed receipt claims; no floating point or AI writes."""

import re
from datetime import date
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator
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

Currency = Literal["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]
MONEY_PATTERN = re.compile(
    r"\bline total\s*:?\s*(USD|EUR|GBP|CAD|AUD|JPY) "
    r"([0-9]+(?:\.[0-9]{2})?)(?![0-9A-Za-z_.,+\-])",
    re.I,
)


def minor_amount(amount: str, currency: str) -> int:
    pattern = (
        r"(?:0|[1-9][0-9]{0,10})"
        if currency == "JPY"
        else r"(?:0|[1-9][0-9]{0,8})\.[0-9]{2}"
    )
    if not re.fullmatch(pattern, amount):
        raise ValueError("Use an exact nonnegative amount with currency precision")
    value = int(amount) if currency == "JPY" else int(amount.replace(".", ""))
    if value > 99999999999:
        raise ValueError("Receipt total exceeds the supported limit")
    return value


class DetailRead(ReceiptRead):
    index: int = Field(ge=0, le=7)
    before_revision: int = Field(default=0, ge=0, le=2147483647)


class DetailSave(ReceiptRead):
    index: int = Field(ge=0, le=7)
    expected_head: str | None = Field(default=None, min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    currency: Currency = "USD"
    line_total: str | None = Field(default=None, min_length=1, max_length=14)
    money_quote: str | None = Field(default=None, min_length=1, max_length=500)
    purchase_date: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
    )
    date_quote: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def exact_money(self) -> Self:
        if self.line_total is not None:
            minor_amount(self.line_total, self.currency)
        return self


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
            "line_total": (
                str(row.total_minor)
                if row.currency == "JPY"
                else f"{row.total_minor // 100}.{row.total_minor % 100:02d}"
            )
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

    @staticmethod
    def suggestions(text: str, item_quote: str) -> dict[str, str | None]:
        """Copy uniquely labeled source passages; never infer or calculate."""
        result: dict[str, str | None] = {
            "line_total": None,
            "currency": None,
            "money_quote": None,
            "purchase_date": None,
            "date_quote": None,
        }
        # Restrict money to the item's own printed line; never borrow another total.
        lines = [line for line in text.splitlines() if item_quote in line]
        if len(lines) == 1 and len(lines[0]) <= 500:
            amounts = MONEY_PATTERN.findall(lines[0])
            if len(amounts) == 1:
                currency, amount = amounts[0]
                try:
                    minor_amount(amount, currency.upper())
                except ValueError:
                    pass
                else:
                    result.update(
                        line_total=amount,
                        currency=currency.upper(),
                        money_quote=lines[0],
                    )
        dates = list(
            re.finditer(
                r"\bpurchase date\s*:?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})(?![0-9])",
                text,
                re.I,
            )
        )
        if len(dates) == 1:
            try:
                date.fromisoformat(dates[0][1])
            except ValueError:
                pass
            else:
                result.update(purchase_date=dates[0][1], date_quote=dates[0][0])
        return result

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
            suggestions = None
            try:
                text = self.receipts.source(db, actor, receipt.source_id)
                suggestions = self.suggestions(text, choice.fields.quote)
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
                "suggestions": suggestions,
                "items": [self.view(r) for r in rows[:5]],
                "next_revision": rows[4].revision if len(rows) > 5 else None,
            }

    def save(self, actor: Account, value: DetailSave) -> dict[str, Any]:
        data = DetailSave.model_validate(value)
        payload = data.model_dump()
        # Preserve old USD fingerprints for lost-response replay.
        if data.currency == "USD":
            payload.pop("currency")
        signature = fingerprint(payload)
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
                amounts = MONEY_PATTERN.findall(quote)
                if [(code.upper(), amount) for code, amount in amounts] != [
                    (data.currency, data.line_total)
                ]:
                    raise MemoryError(
                        "Use one exact Line total: CODE amount passage; "
                        "symbols alone are ambiguous"
                    )
                total = minor_amount(data.line_total, data.currency)
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
                currency=data.currency if total is not None else None,
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
