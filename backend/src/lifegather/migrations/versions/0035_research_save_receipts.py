"""Persist exact research-save requests even when they reuse existing evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0035_research_save_receipts"
down_revision = "0034_research_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_save_receipts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("finding_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "asset_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "finding_id"],
            ["research_findings.user_id", "research_findings.id"],
        ),
    )
    op.create_index(
        "ix_research_save_receipts_user_id", "research_save_receipts", ["user_id"]
    )
    op.execute("ALTER TABLE research_save_receipts ENABLE ROW LEVEL SECURITY")
    account = "current_setting('lifegather.account_id', true)"
    op.execute(
        "CREATE POLICY account_rows ON research_save_receipts TO lifegather_account "
        f"USING (user_id = {account}) WITH CHECK (user_id = {account})"
    )


def downgrade() -> None:
    op.drop_table("research_save_receipts")
