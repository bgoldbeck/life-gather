from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        Index(
            "uq_documents_active_hash",
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
    format: Mapped[str] = mapped_column(default="pdf", server_default="pdf")
    extraction_metadata: Mapped[str] = mapped_column(default="{}", server_default="{}")
    size: Mapped[int]
    pages: Mapped[int]
    extracted_text: Mapped[str]
    text_truncated: Mapped[bool]
    original: Mapped[bytes | None] = mapped_column(deferred=True)
    source_id: Mapped[str | None]
    created_at: Mapped[int]
    updated_at: Mapped[int]
    deleted_at: Mapped[int | None]
