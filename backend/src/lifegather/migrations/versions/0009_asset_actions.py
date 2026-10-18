"""Append-only asset correction/ownership actions."""

import sqlalchemy as sa
from alembic import op

revision = "0009_asset_actions"
down_revision = "0008_asset_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    fields = [
        ("asset_id", "memory_entities", False),
        ("target_asset_id", "memory_entities", True),
        ("previous_id", "asset_actions", True),
        ("source_id", "memory_sources", False),
        ("ownership_fact_id", "memory_facts", True),
        ("status_fact_id", "memory_facts", True),
    ]
    op.create_table(
        "asset_actions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=nullable)
            for name, _, nullable in fields
        ],
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("result_json", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        *[
            sa.ForeignKeyConstraint(
                ["user_id", name], [table + ".user_id", table + ".id"]
            )
            for name, table, _ in fields
        ],
    )
    for column in ("user_id", "asset_id"):
        op.create_index("ix_asset_actions_" + column, "asset_actions", [column])


def downgrade() -> None:
    op.drop_table("asset_actions")
