"""Persistent review before saved-note extraction enters inventory."""

import sqlalchemy as sa
from alembic import op

revision = "0008_asset_proposals"
down_revision = "0007_note_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("proposed_json", sa.String(), nullable=False),
        sa.Column("reviewed_json", sa.String()),
        sa.Column("observation_id", sa.String()),
        sa.Column("request_id", sa.String()),
        sa.Column("fingerprint", sa.String()),
        sa.Column("result_json", sa.String(), nullable=False),
        sa.Column("reviewed_at", sa.Integer()),
        sa.UniqueConstraint("user_id", "source_id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "observation_id"],
            ["reconciliation_observations.user_id", "reconciliation_observations.id"],
        ),
        sa.CheckConstraint("state IN ('proposed','no_item','accepted','rejected')"),
    )
    op.create_index("ix_asset_proposals_user_id", "asset_proposals", ["user_id"])


def downgrade() -> None:
    op.drop_table("asset_proposals")
