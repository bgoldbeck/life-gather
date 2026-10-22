from datetime import date

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


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "entity_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    entity_id: Mapped[str] = mapped_column(index=True)
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]


class MaintenanceRevision(Base):
    __tablename__ = "maintenance_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "task_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        UniqueConstraint("user_id", "previous_id"),
        ForeignKeyConstraint(
            ["user_id", "task_id"],
            ["maintenance_tasks.user_id", "maintenance_tasks.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "task_id", "previous_id"],
            [
                "maintenance_revisions.user_id",
                "maintenance_revisions.task_id",
                "maintenance_revisions.id",
            ],
        ),
        CheckConstraint(
            "state IN ('open','completed','canceled')", name="ck_maintenance_state"
        ),
        CheckConstraint(
            "completed_on IS NULL OR state = 'completed'",
            name="ck_maintenance_completion",
        ),
        CheckConstraint(
            "superseded_at IS NULL OR superseded_at > recorded_at",
            name="ck_maintenance_revision_time",
        ),
        Index(
            "ix_maintenance_current",
            "user_id",
            "task_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index("ix_maintenance_due", "user_id", "state", "superseded_at", "due_on"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[str]
    previous_id: Mapped[str | None]
    title: Mapped[str]
    due_on: Mapped[date | None]
    timezone: Mapped[str]
    state: Mapped[str]
    completed_on: Mapped[date | None]
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]
    superseded_at: Mapped[int | None]
