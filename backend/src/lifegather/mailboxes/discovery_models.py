from sqlalchemy import ForeignKeyConstraint, String
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
