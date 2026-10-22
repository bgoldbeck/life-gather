"""Append-only source associations to existing canonical purchases."""

import sqlalchemy as sa
from alembic import op

revision = "0020_purchase_evidence"
down_revision = "0019_scan_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(key, sa.String(), nullable=False)
            for key in (
                "purchase_id",
                "source_id",
                "root_source_id",
                "state",
                "role",
                "quote",
                "reason",
                "request_id",
                "fingerprint",
            )
        ],
        *[
            sa.Column(key, sa.String())
            for key in (
                "previous_id",
                "currency",
                "money_quote",
                "occurred_on",
                "date_quote",
            )
        ],
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.Integer()),
        sa.Column("amount_minor", sa.Integer()),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.UniqueConstraint("user_id", "root_source_id", "revision"),
        *[
            sa.ForeignKeyConstraint(
                ["user_id", key], [table + ".user_id", table + ".id"]
            )
            for key, table in (
                ("purchase_id", "reconciliation_purchases"),
                ("source_id", "memory_sources"),
                ("root_source_id", "memory_sources"),
                ("previous_id", "purchase_evidence"),
            )
        ],
        sa.CheckConstraint(
            "role IN ('order','receipt','shipment','payment') "
            "AND state IN ('active','withdrawn') AND revision >= 1"
        ),
        sa.CheckConstraint("(amount_minor IS NULL) = (currency IS NULL)"),
        sa.CheckConstraint(
            "amount_minor IS NULL OR (amount_minor BETWEEN 0 AND 99999999999 "
            "AND currency IN ('USD','EUR','GBP','CAD','AUD','JPY'))"
        ),
    )
    op.create_index("ix_purchase_evidence_user_id", "purchase_evidence", ["user_id"])
    op.create_index(
        "uq_purchase_evidence_head",
        "purchase_evidence",
        ["user_id", "root_source_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_purchase_evidence_group",
        "purchase_evidence",
        ["user_id", "purchase_id", "superseded_at"],
    )


def downgrade() -> None:
    op.drop_table("purchase_evidence")
