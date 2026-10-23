from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class OperationalEvent(Base):
    """One kind of installation problem, counted; never personal content.

    A system table: it has no owner, and the per-account database role has no
    access to it (migration 0038).
    """

    __tablename__ = "operational_events"
    __table_args__ = (CheckConstraint("level IN ('error','critical')"),)
    fingerprint: Mapped[str] = mapped_column(primary_key=True)
    level: Mapped[str]
    logger: Mapped[str]
    message: Mapped[str]
    detail_json: Mapped[str]
    count: Mapped[int]
    first_at: Mapped[int]
    last_at: Mapped[int] = mapped_column(index=True)
    alerted_at: Mapped[int | None]
