from datetime import date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class Episode(Base):
    __tablename__ = "memory_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "source_key"),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_key: Mapped[str]
    text: Mapped[str]
    source_type: Mapped[str]
    namespace: Mapped[str]
    external_id: Mapped[str | None]
    content_hash: Mapped[str]
    event_date: Mapped[date | None]
    recorded_at: Mapped[int]


class Entity(Base):
    __tablename__ = "memory_entities"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "operation_key"),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str]
    normalized_name: Mapped[str]
    kind: Mapped[str]
    source_id: Mapped[str]
    operation_key: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]


class Alias(Base):
    __tablename__ = "memory_aliases"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", "normalized_name", "source_id"),
        ForeignKeyConstraint(
            ["user_id", "entity_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    entity_id: Mapped[str]
    name: Mapped[str]
    normalized_name: Mapped[str]
    source_id: Mapped[str]
    recorded_at: Mapped[int]


class Assertion(Base):
    __tablename__ = "memory_facts"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "operation_key"),
        ForeignKeyConstraint(
            ["user_id", "subject_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "object_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "replaces_id"], ["memory_facts.user_id", "memory_facts.id"]
        ),
        CheckConstraint(
            "(object_id IS NULL AND value_json IS NOT NULL) "
            "OR (object_id IS NOT NULL AND value_json IS NULL)",
            name="ck_fact_object_xor_literal",
        ),
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from < valid_to",
            name="ck_fact_dates",
        ),
        CheckConstraint(
            "status IN ('stated','verified','inferred','unknown')",
            name="ck_fact_status",
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[str] = mapped_column(index=True)
    predicate: Mapped[str]
    object_id: Mapped[str | None] = mapped_column(index=True)
    value_json: Mapped[str | None]
    status: Mapped[str]
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    recorded_at: Mapped[int]
    superseded_at: Mapped[int | None]
    replaces_id: Mapped[str | None]
    operation_key: Mapped[str]
    fingerprint: Mapped[str]


class Evidence(Base):
    __tablename__ = "memory_evidence"
    __table_args__ = (
        UniqueConstraint("user_id", "fact_id", "source_id"),
        ForeignKeyConstraint(
            ["user_id", "fact_id"], ["memory_facts.user_id", "memory_facts.id"]
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    fact_id: Mapped[str]
    source_id: Mapped[str]
    quote: Mapped[str | None]
    recorded_at: Mapped[int]


class Audit(Base):
    __tablename__ = "memory_audit"
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str]
    target_id: Mapped[str]
    recorded_at: Mapped[int]


class NoteRevision(Base):
    __tablename__ = "memory_note_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id"),
        UniqueConstraint("user_id", "previous_source_id"),
        UniqueConstraint("user_id", "source_id"),
        ForeignKeyConstraint(
            ["user_id", "root_source_id"],
            ["memory_sources.user_id", "memory_sources.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "previous_source_id"],
            ["memory_sources.user_id", "memory_sources.id"],
        ),
        ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        CheckConstraint(
            "source_id != previous_source_id AND source_id != root_source_id"
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    root_source_id: Mapped[str] = mapped_column(index=True)
    previous_source_id: Mapped[str]
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    recorded_at: Mapped[int]
