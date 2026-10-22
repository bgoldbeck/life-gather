from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class PurchaseEvidence(Base):
    __tablename__ = "purchase_evidence"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        UniqueConstraint("user_id", "root_source_id", "revision"),
        ForeignKeyConstraint(
            ["user_id", "purchase_id"],
            ["reconciliation_purchases.user_id", "reconciliation_purchases.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "root_source_id"],
            ["memory_sources.user_id", "memory_sources.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "previous_id"],
            ["purchase_evidence.user_id", "purchase_evidence.id"],
        ),
        CheckConstraint(
            "role IN ('order','receipt','shipment','payment') "
            "AND state IN ('active','withdrawn') AND revision >= 1"
        ),
        CheckConstraint("(amount_minor IS NULL) = (currency IS NULL)"),
        CheckConstraint(
            "amount_minor IS NULL OR (amount_minor BETWEEN 0 AND 99999999999 "
            "AND currency IN ('USD','EUR','GBP','CAD','AUD','JPY'))"
        ),
        Index(
            "uq_purchase_evidence_head",
            "user_id",
            "root_source_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index("ix_purchase_evidence_group", "user_id", "purchase_id", "superseded_at"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purchase_id: Mapped[str]
    source_id: Mapped[str]
    root_source_id: Mapped[str]
    revision: Mapped[int]
    previous_id: Mapped[str | None]
    superseded_at: Mapped[int | None]
    state: Mapped[str]
    role: Mapped[str]
    quote: Mapped[str]
    amount_minor: Mapped[int | None]
    currency: Mapped[str | None]
    money_quote: Mapped[str | None]
    occurred_on: Mapped[str | None]
    date_quote: Mapped[str | None]
    reason: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]
