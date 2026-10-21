"""Private template definitions; asset values remain sourced memory facts."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class AssetType(Base):
    __tablename__ = "asset_types"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "seed_key"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    seed_key: Mapped[str | None]
    name: Mapped[str]
    description: Mapped[str]
    retired: Mapped[bool]
    revision: Mapped[str]


class AssetTypeField(Base):
    __tablename__ = "asset_type_fields"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "type_id"], ["asset_types.user_id", "asset_types.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    system_field: Mapped[str | None]
    retired: Mapped[bool]
    position: Mapped[int]


class AssetTypeRevision(Base):
    __tablename__ = "asset_type_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "type_id"], ["asset_types.user_id", "asset_types.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "previous_id"],
            ["asset_type_revisions.user_id", "asset_type_revisions.id"],
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type_id: Mapped[str] = mapped_column(index=True)
    previous_id: Mapped[str | None]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    definition_json: Mapped[str]
    recorded_at: Mapped[int]
