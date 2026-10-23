from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class EmailDiscovery(Base):
    """Completed extraction cache; sources and decisions retain original history."""

    __tablename__ = "email_discoveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    result_json: Mapped[str]
    extraction_json: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    recorded_at: Mapped[int]


class EmailAttachment(Base):
    """Provenance link from a saved email source to a file saved from it."""

    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint("user_id", "source_id", "part_id", "document_id"),
        UniqueConstraint(
            "user_id",
            "source_id",
            "part_id",
            "photo_id",
            name="uq_email_attachments_photo",
        ),
        CheckConstraint(
            "(document_id IS NULL) <> (photo_id IS NULL)",
            name="ck_email_attachments_one_file",
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id"], ["documents.user_id", "documents.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "photo_id"],
            ["photos.user_id", "photos.id"],
            name="fk_email_attachments_photo",
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String)
    document_id: Mapped[str | None] = mapped_column(String, index=True)
    photo_id: Mapped[str | None] = mapped_column(String, index=True)
    mailbox_id: Mapped[str] = mapped_column(String)
    message_id: Mapped[str] = mapped_column(String)
    part_id: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    recorded_at: Mapped[int]
