from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class ResearchFinding(Base):
    """One cited web source the user saved to an asset from a research reply."""

    __tablename__ = "research_findings"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "asset_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        # At most one active copy of a page per asset; removed rows stay as history.
        Index(
            "ux_research_findings_active",
            "user_id",
            "asset_id",
            "url",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    asset_id: Mapped[str] = mapped_column(index=True)
    request_id: Mapped[str]
    # The research turn it came from; no foreign key, so deleting the
    # conversation keeps the saved copy.
    turn_id: Mapped[str]
    question: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    researched_at: Mapped[str]
    url: Mapped[str]
    title: Mapped[str]
    published: Mapped[str | None]
    excerpt_kind: Mapped[str]
    excerpts_json: Mapped[str]
    recorded_at: Mapped[int]
    removed_at: Mapped[int | None]
