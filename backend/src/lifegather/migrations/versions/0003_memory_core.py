"""Private evidence-backed entities, assertions, and source search."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0003_memory_core"
down_revision = "0002_private_settings"
branch_labels = None
depends_on = None


def owner() -> sa.Column[str]:
    return sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False)


def identity() -> sa.Column[str]:
    return sa.Column("id", sa.String(), primary_key=True)


def link(column: str, table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id", column], [table + ".user_id", table + ".id"]
    )


def upgrade() -> None:
    op.create_table(
        "memory_sources",
        identity(),
        owner(),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("external_id", sa.String()),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("event_date", sa.Date()),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "source_key"),
    )
    op.create_table(
        "memory_entities",
        identity(),
        owner(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("operation_key", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "operation_key"),
        link("source_id", "memory_sources"),
    )
    op.create_table(
        "memory_aliases",
        identity(),
        owner(),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "entity_id", "normalized_name", "source_id"),
        link("entity_id", "memory_entities"),
        link("source_id", "memory_sources"),
    )
    op.create_table(
        "memory_facts",
        identity(),
        owner(),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("predicate", sa.String(), nullable=False),
        sa.Column("object_id", sa.String()),
        sa.Column("value_json", sa.String()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.Integer()),
        sa.Column("replaces_id", sa.String()),
        sa.Column("operation_key", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "operation_key"),
        link("subject_id", "memory_entities"),
        link("object_id", "memory_entities"),
        link("replaces_id", "memory_facts"),
        sa.CheckConstraint(
            "(object_id IS NULL AND value_json IS NOT NULL) "
            "OR (object_id IS NOT NULL AND value_json IS NULL)",
            name="ck_fact_object_xor_literal",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from < valid_to",
            name="ck_fact_dates",
        ),
        sa.CheckConstraint(
            "status IN ('stated','verified','inferred','unknown')",
            name="ck_fact_status",
        ),
    )
    op.create_table(
        "memory_evidence",
        identity(),
        owner(),
        sa.Column("fact_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("quote", sa.String()),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "fact_id", "source_id"),
        link("fact_id", "memory_facts"),
        link("source_id", "memory_sources"),
    )
    op.create_table(
        "memory_audit",
        identity(),
        owner(),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
    )
    for table in ("sources", "entities", "aliases", "facts", "evidence", "audit"):
        op.create_index(
            "ix_memory_" + table + "_user_id", "memory_" + table, ["user_id"]
        )
    for column in ("subject_id", "object_id"):
        op.create_index("ix_memory_facts_" + column, "memory_facts", [column])
    # Owner-scoped word index: folded Unicode words in a GIN-indexed text array.
    op.create_table(
        "memory_fts",
        sa.Column("record_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("terms", ARRAY(sa.String()), nullable=False),
    )
    op.create_index(
        "ix_memory_fts_record", "memory_fts", ["user_id", "record_id", "kind"]
    )
    op.create_index(
        "ix_memory_fts_terms", "memory_fts", ["terms"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("memory_fts")
    for table in ("audit", "evidence", "facts", "aliases", "entities", "sources"):
        op.drop_table("memory_" + table)
