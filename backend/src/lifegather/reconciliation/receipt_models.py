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
