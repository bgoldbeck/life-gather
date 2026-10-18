from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class ReceiptProposal(Base):
    __tablename__ = "receipt_proposals"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "source_id"),
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        CheckConstraint("state IN ('proposed','no_items','accepted','rejected')"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str]
    state: Mapped[str]
    proposed_json: Mapped[str]
    reviewed_json: Mapped[str | None]
    result_json: Mapped[str]
    request_id: Mapped[str | None]
    fingerprint: Mapped[str | None]
    recorded_at: Mapped[int]
    reviewed_at: Mapped[int | None]


class ReceiptDetail(Base):
    """Immutable typed claims about one reviewed receipt line, never unit prices."""

    __tablename__ = "receipt_details"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        UniqueConstraint("user_id", "receipt_id", "line_index", "revision"),
        ForeignKeyConstraint(
            ["user_id", "receipt_id"],
            ["receipt_proposals.user_id", "receipt_proposals.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        CheckConstraint("line_index BETWEEN 0 AND 7 AND revision >= 1"),
        CheckConstraint(
            "total_minor IS NULL OR (total_minor BETWEEN 0 AND 99999999999 "
            "AND currency IN ('USD','EUR','GBP','CAD','AUD','JPY'))"
        ),
        CheckConstraint("(total_minor IS NULL) = (currency IS NULL)"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    receipt_id: Mapped[str]
    source_id: Mapped[str]
    line_index: Mapped[int]
    revision: Mapped[int]
    total_minor: Mapped[int | None]
    currency: Mapped[str | None]
    money_quote: Mapped[str | None]
    purchase_date: Mapped[str | None]
    date_quote: Mapped[str | None]
    reason: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]
