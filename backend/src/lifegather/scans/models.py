from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        CheckConstraint(
            "state IN ('queued','running','completed','failed','canceled')"
        ),
        CheckConstraint("scanned BETWEEN 0 AND 50 AND steps BETWEEN 0 AND 100"),
        Index(
            "uq_active_scan_resource",
            "user_id",
            "resource_key",
            unique=True,
            sqlite_where=text("state IN ('queued','running')"),
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    handler_key: Mapped[str]
    resource_key: Mapped[str]
    config_json: Mapped[str]
    cursor_json: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    state: Mapped[str] = mapped_column(index=True)
    cancel_requested: Mapped[bool]
    scanned: Mapped[int]
    imported: Mapped[int]
    existing: Mapped[int]
    skipped: Mapped[int]
    steps: Mapped[int]
    attempts: Mapped[int]
    truncated: Mapped[bool]
    error: Mapped[str | None]
    lease_token: Mapped[str | None]
    lease_until: Mapped[int | None]
    created_at: Mapped[int]
    updated_at: Mapped[int]
    started_at: Mapped[int | None]
    completed_at: Mapped[int | None]


class ScanRunItem(Base):
    __tablename__ = "scan_run_items"
    __table_args__ = (
        UniqueConstraint("user_id", "run_id", "item_key"),
        UniqueConstraint("user_id", "run_id", "sequence"),
        ForeignKeyConstraint(
            ["user_id", "run_id"], ["scan_runs.user_id", "scan_runs.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[str] = mapped_column(index=True)
    sequence: Mapped[int]
    item_key: Mapped[str]
    source_id: Mapped[str | None]
    label: Mapped[str]
    state: Mapped[str]
    reason: Mapped[str]
    metadata_json: Mapped[str]
