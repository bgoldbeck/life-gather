from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class AssetProposal(Base):
    __tablename__ = "asset_proposals"
    __table_args__ = (
        UniqueConstraint("user_id", "source_id"),
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "observation_id"],
            ["reconciliation_observations.user_id", "reconciliation_observations.id"],
        ),
        CheckConstraint("state IN ('proposed','no_item','accepted','rejected')"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str]
    recorded_at: Mapped[int]
    state: Mapped[str]
    proposed_json: Mapped[str]
    reviewed_json: Mapped[str | None]
    observation_id: Mapped[str | None]
    request_id: Mapped[str | None]
    fingerprint: Mapped[str | None]
    result_json: Mapped[str]
    reviewed_at: Mapped[int | None]
