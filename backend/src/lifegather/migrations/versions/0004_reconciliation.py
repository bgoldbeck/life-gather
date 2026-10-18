"""Owner-scoped discovery observations, purchased units and reversible decisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.schema import SchemaItem

revision = "0004_reconciliation"
down_revision = "0003_memory_core"
branch_labels = None
depends_on = None


def link(column: str, table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id", column], [table + ".user_id", table + ".id"]
    )


def create(name: str, *columns: SchemaItem) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        *columns,
    )
    op.create_index("ix_" + name + "_user_id", name, ["user_id"])


def string(name: str, nullable: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.String(), nullable=nullable)


def upgrade() -> None:
    create(
        "reconciliation_purchases",
        string("identity_key"),
        string("retailer"),
        string("account_scope"),
        string("order_id"),
        string("source_id"),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "identity_key"),
        link("source_id", "memory_sources"),
    )
    create(
        "reconciliation_lines",
        string("purchase_id"),
        string("line_key"),
        string("product_id", True),
        string("source_id"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "purchase_id", "line_key"),
        link("purchase_id", "reconciliation_purchases"),
        link("product_id", "memory_entities"),
        link("source_id", "memory_sources"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 20"),
    )
    create(
        "reconciliation_observations",
        string("source_id"),
        string("item_key"),
        string("payload"),
        string("fingerprint"),
        string("product_id", True),
        string("line_id", True),
        string("serial_key", True),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "source_id", "item_key"),
        link("source_id", "memory_sources"),
        link("product_id", "memory_entities"),
        link("line_id", "reconciliation_lines"),
    )
    op.create_index(
        "ix_reconciliation_observations_serial_key",
        "reconciliation_observations",
        ["serial_key"],
    )
    create(
        "reconciliation_decisions",
        string("observation_id"),
        string("previous_id", True),
        string("outcome"),
        string("reason"),
        string("request_key"),
        sa.Column("superseded_at", sa.Integer()),
        sa.UniqueConstraint("user_id", "id"),
        link("observation_id", "reconciliation_observations"),
        link("previous_id", "reconciliation_decisions"),
        sa.CheckConstraint("outcome IN ('create','enrich','review','dismissed')"),
    )
    op.create_index(
        "uq_reconciliation_current",
        "reconciliation_decisions",
        ["user_id", "observation_id"],
        unique=True,
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    create(
        "reconciliation_bindings",
        string("decision_id"),
        sa.Column("unit", sa.Integer(), nullable=False),
        string("asset_id"),
        string("ownership_fact_id"),
        string("product_fact_id", True),
        sa.UniqueConstraint("user_id", "decision_id", "unit"),
        link("decision_id", "reconciliation_decisions"),
        link("asset_id", "memory_entities"),
        link("ownership_fact_id", "memory_facts"),
        link("product_fact_id", "memory_facts"),
        sa.CheckConstraint("unit BETWEEN 0 AND 19"),
    )
    create(
        "reconciliation_candidates",
        string("decision_id"),
        string("asset_id"),
        sa.UniqueConstraint("user_id", "decision_id", "asset_id"),
        link("decision_id", "reconciliation_decisions"),
        link("asset_id", "memory_entities"),
    )


def downgrade() -> None:
    for name in (
        "candidates",
        "bindings",
        "decisions",
        "observations",
        "lines",
        "purchases",
    ):
        op.drop_table("reconciliation_" + name)
