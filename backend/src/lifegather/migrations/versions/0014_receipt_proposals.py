"""Durable reviewed multi-item receipt drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0014_receipt_proposals"
down_revision = "0013_private_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipt_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in ("state", "proposed_json", "result_json")
        ],
        *[
            sa.Column(name, sa.String(), nullable=True)
            for name in ("reviewed_json", "request_id", "fingerprint")
        ],
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.Integer(), nullable=True),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "source_id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        sa.CheckConstraint("state IN ('proposed','no_items','accepted','rejected')"),
    )
    op.create_index("ix_receipt_proposals_user_id", "receipt_proposals", ["user_id"])


def downgrade() -> None:
    op.drop_table("receipt_proposals")
