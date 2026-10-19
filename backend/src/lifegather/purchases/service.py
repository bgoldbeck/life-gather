"""Reviewed cross-source purchase associations, independent of HTTP and models."""

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.service import (
    MemoryError,
    MemoryService,
    fingerprint,
    normalized,
)
from lifegather.purchases.models import PurchaseEvidence
from lifegather.purchases.schemas import EvidenceSave, EvidenceWithdraw
from lifegather.reconciliation.models import (
    Binding,
    Decision,
    Observation,
    Purchase,
    PurchaseLine,
)
from lifegather.reconciliation.purchase_details import minor_amount
from lifegather.reconciliation.purchase_identity import purchase_in
from lifegather.reconciliation.receipts import ReceiptService

MONEY = re.compile(
    r"\b(USD|EUR|GBP|CAD|AUD|JPY)\s+([0-9]+(?:\.[0-9]+)?)(?![0-9A-Za-z_.,+\-])", re.I
)
DATES = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")


class PurchaseEvidenceService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.receipts = ReceiptService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> Purchase:
        row = db.scalar(
            select(Purchase).where(
                Purchase.user_id == actor.id, Purchase.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Purchase not found")
        return row

    def source_text(self, db: Session, actor: Account, identifier: str) -> str:
        source = self.memory._source(db, actor, identifier)
        return (
            self.receipts.source(db, actor, identifier)
            if NoteService.is_note(source)
            else source.text
        )

    @staticmethod
    def head(db: Session, actor: Account, root: str) -> PurchaseEvidence | None:
        return db.scalar(
            select(PurchaseEvidence).where(
                PurchaseEvidence.user_id == actor.id,
                PurchaseEvidence.root_source_id == root,
                PurchaseEvidence.superseded_at.is_(None),
            )
        )

    def current(self, db: Session, actor: Account, row: PurchaseEvidence) -> bool:
        try:
            self.source_text(db, actor, row.source_id)
            return True
        except MemoryError:
            return False

    def view(
        self, db: Session, actor: Account, row: PurchaseEvidence
    ) -> dict[str, Any]:
        keys = (
            "id",
            "purchase_id",
            "source_id",
            "root_source_id",
            "revision",
            "previous_id",
            "superseded_at",
            "state",
            "role",
            "quote",
            "amount_minor",
            "currency",
            "money_quote",
            "occurred_on",
            "date_quote",
            "reason",
            "recorded_at",
        )
        return {
            **{key: getattr(row, key) for key in keys},
            "source_current": self.current(db, actor, row),
        }

    @staticmethod
    def purchase_view(row: Purchase) -> dict[str, Any]:
        return {
            "id": row.id,
            "retailer": row.retailer,
            "account_scope": row.account_scope,
            "order_id": row.order_id,
            "original_source_id": row.source_id,
            "recorded_at": row.recorded_at,
        }

    def list(self, actor: Account, cursor: str = "", limit: int = 10) -> dict[str, Any]:
        if not 1 <= limit <= 20:
            raise MemoryError("Invalid purchase page size")
        with Session(self.engine) as db:
            if cursor:
                self.owned(db, actor, cursor)
            rows = list(
                db.scalars(
                    select(Purchase)
                    .where(Purchase.user_id == actor.id, Purchase.id > cursor)
                    .order_by(Purchase.id)
                    .limit(limit + 1)
                )
            )
            return {
                "items": [self.purchase_view(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }

    def get(
        self, actor: Account, identifier: str, after: str = "", limit: int = 5
    ) -> dict[str, Any]:
        if not 1 <= limit <= 10:
            raise MemoryError("Invalid evidence page size")
        with Session(self.engine) as db:
            purchase = self.owned(db, actor, identifier)
            query = select(PurchaseEvidence).where(
                PurchaseEvidence.user_id == actor.id,
                PurchaseEvidence.purchase_id == identifier,
                PurchaseEvidence.superseded_at.is_(None),
                PurchaseEvidence.state == "active",
            )
            all_rows = list(db.scalars(query.order_by(PurchaseEvidence.id).limit(50)))
            if after and not any(row.id == after for row in all_rows):
                raise MemoryError("Invalid purchase evidence cursor")
            rows = [row for row in all_rows if row.id > after]
            totals = {
                (row.currency, row.amount_minor)
                for row in all_rows
                if row.role in {"order", "receipt"}
                and row.amount_minor is not None
                and self.current(db, actor, row)
            }
            assets = list(
                db.scalars(
                    select(Binding.asset_id)
                    .join(Decision, Decision.id == Binding.decision_id)
                    .join(Observation, Observation.id == Decision.observation_id)
                    .join(PurchaseLine, PurchaseLine.id == Observation.line_id)
                    .where(
                        Binding.user_id == actor.id,
                        Decision.user_id == actor.id,
                        Observation.user_id == actor.id,
                        PurchaseLine.user_id == actor.id,
                        PurchaseLine.purchase_id == identifier,
                        Decision.superseded_at.is_(None),
                        Decision.outcome.in_(["create", "enrich"]),
                    )
                    .distinct()
                    .order_by(Binding.asset_id)
                    .limit(21)
                )
            )
            return {
                **self.purchase_view(purchase),
                "items": [self.view(db, actor, row) for row in rows[:limit]],
                "next_after": rows[limit - 1].id if len(rows) > limit else None,
                "active_source_count": len(all_rows),
                "conflicting_totals": len(totals) > 1,
                "linked_asset_ids": assets[:20],
                "assets_truncated": len(assets) > 20,
                "amounts_are_not_summed": True,
            }

    def source_context(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, identifier)
            root = NoteService._root(db, actor, source)
            head = self.head(db, actor, root)
            try:
                self.source_text(db, actor, identifier)
                available = True
            except MemoryError:
                available = False
            return {
                "source_id": source.id,
                "text": source.text,
                "root_source_id": root,
                "current_source_id": NoteService._head(db, actor, root),
                "can_attach": available,
                "head": self.view(db, actor, head) if head else None,
            }

    def history(
        self, actor: Account, identifier: str, before_revision: int = 0
    ) -> dict[str, Any]:
        if before_revision < 0:
            raise MemoryError("Invalid evidence history cursor")
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, identifier)
            root = NoteService._root(db, actor, source)
            query = select(PurchaseEvidence).where(
                PurchaseEvidence.user_id == actor.id,
                PurchaseEvidence.root_source_id == root,
            )
            if before_revision:
                query = query.where(PurchaseEvidence.revision < before_revision)
            rows = list(
                db.scalars(query.order_by(PurchaseEvidence.revision.desc()).limit(6))
            )
            return {
                "items": [self.view(db, actor, row) for row in rows[:5]],
                "next_revision": rows[4].revision if len(rows) > 5 else None,
            }

    def replay(
        self, db: Session, actor: Account, request_id: str, signature: str
    ) -> dict[str, Any] | None:
        row = db.scalar(
            select(PurchaseEvidence).where(
                PurchaseEvidence.user_id == actor.id,
                PurchaseEvidence.request_id == request_id,
            )
        )
        if row is not None:
            if row.fingerprint != signature:
                raise NoteConflict("Purchase evidence request conflict")
            return self.view(db, actor, row)
        return None

    def save(self, actor: Account, value: EvidenceSave) -> dict[str, Any]:
        data = EvidenceSave.model_validate(value)
        signature = fingerprint(["attach", data.model_dump()])
        with self.memory._write() as db:
            old = self.replay(db, actor, data.request_id, signature)
            if old:
                return old
            source = self.memory._source(db, actor, data.source_id)
            root = NoteService._root(db, actor, source)
            text = self.source_text(db, actor, source.id)
            if data.quote not in text:
                raise MemoryError(
                    "Evidence quote must appear exactly in the saved source"
                )
            head = self.head(db, actor, root)
            if (head.id if head else None) != data.expected_head:
                raise NoteConflict(
                    "Purchase evidence changed; reload before correcting"
                )
            total = None
            if data.amount is not None:
                quote = data.money_quote or ""
                if quote not in data.quote or [
                    (code.upper(), amount) for code, amount in MONEY.findall(quote)
                ] != [(data.currency, data.amount)]:
                    raise MemoryError(
                        "Quote one currency-coded amount within the evidence quote"
                    )
                total = minor_amount(data.amount, data.currency)
            if data.occurred_on is not None:
                quote = data.date_quote or ""
                if quote not in data.quote or DATES.findall(quote) != [
                    data.occurred_on
                ]:
                    raise MemoryError(
                        "Quote one matching event date within the evidence quote"
                    )
            now = self.memory.clock()
            if data.purchase_id:
                purchase = self.owned(db, actor, data.purchase_id)
            else:
                assert (
                    data.retailer is not None
                    and data.account_scope is not None
                    and data.order_id is not None
                )
                retailer_match = re.search(
                    r"(?<!\w)" + re.escape(normalized(data.retailer)) + r"(?!\w)",
                    normalized(data.quote),
                )
                order_match = re.search(
                    r"(?<![\w./-])" + re.escape(data.order_id) + r"(?![\w/-]|\.[\w])",
                    data.quote,
                )
                if not retailer_match or not order_match:
                    raise MemoryError(
                        "Retailer and order ID must appear in the evidence quote"
                    )
                purchase = purchase_in(
                    db,
                    actor,
                    source.id,
                    data.retailer,
                    data.account_scope,
                    data.order_id,
                    now,
                    create=data.role != "payment",
                )
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(PurchaseEvidence)
                    .where(
                        PurchaseEvidence.user_id == actor.id,
                        PurchaseEvidence.purchase_id == purchase.id,
                        PurchaseEvidence.state == "active",
                        PurchaseEvidence.superseded_at.is_(None),
                    )
                )
                or 0
            )
            if count >= 50 and not (
                head and head.purchase_id == purchase.id and head.state == "active"
            ):
                raise MemoryError(
                    "Purchase evidence limit reached (50 current sources)"
                )
            if head:
                head.superseded_at = now
                db.flush()
            row = PurchaseEvidence(
                id=str(uuid4()),
                user_id=actor.id,
                purchase_id=purchase.id,
                source_id=source.id,
                root_source_id=root,
                revision=head.revision + 1 if head else 1,
                previous_id=head.id if head else None,
                superseded_at=None,
                state="active",
                role=data.role,
                quote=data.quote,
                amount_minor=total,
                currency=data.currency if total is not None else None,
                money_quote=data.money_quote,
                occurred_on=data.occurred_on,
                date_quote=data.date_quote,
                reason=data.reason,
                request_id=data.request_id,
                fingerprint=signature,
                recorded_at=now,
            )
            db.add(row)
            db.flush()
            self.memory._audit(db, actor, "purchase_evidence_attached", row.id, now)
            return self.view(db, actor, row)

    def withdraw(self, actor: Account, value: EvidenceWithdraw) -> dict[str, Any]:
        data = EvidenceWithdraw.model_validate(value)
        signature = fingerprint(["withdraw", data.model_dump()])
        with self.memory._write() as db:
            old = self.replay(db, actor, data.request_id, signature)
            if old:
                return old
            source = self.memory._source(db, actor, data.source_id)
            root = NoteService._root(db, actor, source)
            head = self.head(db, actor, root)
            if head is None or head.id != data.expected_head or head.state != "active":
                raise NoteConflict(
                    "Purchase evidence changed; reload before withdrawal"
                )
            now = self.memory.clock()
            head.superseded_at = now
            db.flush()
            copied = {
                key: getattr(head, key)
                for key in (
                    "purchase_id",
                    "source_id",
                    "root_source_id",
                    "role",
                    "quote",
                    "amount_minor",
                    "currency",
                    "money_quote",
                    "occurred_on",
                    "date_quote",
                )
            }
            row = PurchaseEvidence(
                **copied,
                id=str(uuid4()),
                user_id=actor.id,
                revision=head.revision + 1,
                previous_id=head.id,
                superseded_at=None,
                state="withdrawn",
                reason=data.reason,
                request_id=data.request_id,
                fingerprint=signature,
                recorded_at=now,
            )
            db.add(row)
            db.flush()
            self.memory._audit(db, actor, "purchase_evidence_withdrawn", row.id, now)
            return self.view(db, actor, row)
