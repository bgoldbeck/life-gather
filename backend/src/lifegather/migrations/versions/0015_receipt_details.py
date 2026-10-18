"""Immutable exact-money and purchase-date receipt claims."""

import sqlalchemy as sa
from alembic import op

revision = "0015_receipt_details"
down_revision = "0014_receipt_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipt_details",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "receipt_id",
                "source_id",
                "reason",
                "request_id",
                "fingerprint",
            )
        ],
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("line_index", "revision", "recorded_at")
        ],
        sa.Column("total_minor", sa.Integer(), nullable=True),
        *[
            sa.Column(name, sa.String(), nullable=True)
            for name in ("currency", "money_quote", "purchase_date", "date_quote")
        ],
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.UniqueConstraint("user_id", "receipt_id", "line_index", "revision"),
        sa.ForeignKeyConstraint(
            ["user_id", "receipt_id"],
            ["receipt_proposals.user_id", "receipt_proposals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        sa.CheckConstraint("line_index BETWEEN 0 AND 7 AND revision >= 1"),
        sa.CheckConstraint(
            "total_minor IS NULL OR (total_minor BETWEEN 0 AND 99999999999 "
            "AND currency = 'USD')"
        ),
        sa.CheckConstraint("(total_minor IS NULL) = (currency IS NULL)"),
    )
    op.create_index("ix_receipt_details_user_id", "receipt_details", ["user_id"])


def downgrade() -> None:
    op.drop_table("receipt_details")
