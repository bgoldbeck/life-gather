from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class AssetAction(Base):
    __tablename__ = "asset_actions"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        *[
            ForeignKeyConstraint(
                ["user_id", field], [table + ".user_id", table + ".id"]
            )
            for field, table in (
                ("asset_id", "memory_entities"),
                ("target_asset_id", "memory_entities"),
                ("source_id", "memory_sources"),
                ("previous_id", "asset_actions"),
                ("ownership_fact_id", "memory_facts"),
                ("status_fact_id", "memory_facts"),
            )
        ],
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    asset_id: Mapped[str] = mapped_column(index=True)
    target_asset_id: Mapped[str | None]
    previous_id: Mapped[str | None]
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    operation: Mapped[str]
    ownership_fact_id: Mapped[str | None]
    status_fact_id: Mapped[str | None]
    result_json: Mapped[str]
    recorded_at: Mapped[int]


class AssetConsolidation(Base):
    """Immutable identity choice, with an explicitly recorded later reversal."""

    __tablename__ = "asset_consolidations"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        UniqueConstraint("user_id", "reverse_request_id"),
        CheckConstraint("primary_id != secondary_id", name="ck_consolidation_pair"),
        CheckConstraint(
            "superseded_at IS NULL OR superseded_at > recorded_at",
            name="ck_consolidation_time",
        ),
        *[
            ForeignKeyConstraint(
                ["user_id", field], [table + ".user_id", table + ".id"]
            )
            for field, table in (
                ("primary_id", "memory_entities"),
                ("secondary_id", "memory_entities"),
                ("source_id", "memory_sources"),
                ("reverse_source_id", "memory_sources"),
            )
        ],
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    primary_id: Mapped[str]
    secondary_id: Mapped[str]
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    state_token: Mapped[str]
    recorded_at: Mapped[int]
    superseded_at: Mapped[int | None]
    reverse_source_id: Mapped[str | None]
    reverse_request_id: Mapped[str | None]
    reverse_fingerprint: Mapped[str | None]


class ConsolidationMember(Base):
    """Two active members; the primary key prevents overlapping identity groups."""

    __tablename__ = "asset_consolidation_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entity_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "consolidation_id"],
            ["asset_consolidations.user_id", "asset_consolidations.id"],
        ),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    entity_id: Mapped[str] = mapped_column(primary_key=True)
    consolidation_id: Mapped[str] = mapped_column(index=True)
