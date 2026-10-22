from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        Index(
            "uq_photos_active_hash",
            "user_id",
            "content_hash",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    content_hash: Mapped[str]
    filename: Mapped[str]
    mime: Mapped[str]
    purpose: Mapped[str]
    size: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    preview_size: Mapped[int]
    original: Mapped[bytes | None] = mapped_column(deferred=True)
    preview: Mapped[bytes | None] = mapped_column(deferred=True)
    original_key: Mapped[str | None] = mapped_column(deferred=True)
    preview_key: Mapped[str | None] = mapped_column(deferred=True)
    source_id: Mapped[str | None]
    created_at: Mapped[int]
    updated_at: Mapped[int]
    deleted_at: Mapped[int | None]


class PhotoAsset(Base):
    __tablename__ = "photo_assets"
    __table_args__ = (
        UniqueConstraint("user_id", "photo_id", "asset_id"),
        ForeignKeyConstraint(["user_id", "photo_id"], ["photos.user_id", "photos.id"]),
        ForeignKeyConstraint(
            ["user_id", "asset_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    photo_id: Mapped[str] = mapped_column(index=True)
    asset_id: Mapped[str] = mapped_column(index=True)
    recorded_at: Mapped[int]
