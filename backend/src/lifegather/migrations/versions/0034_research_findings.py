"""Keep cited web research sources the user saved to an asset."""

import sqlalchemy as sa
from alembic import op

revision = "0034_research_findings"
down_revision = "0033_account_row_security"
branch_labels = None
depends_on = None

ROLE = "lifegather_account"
ACCOUNT = "current_setting('lifegather.account_id', true)"


def upgrade() -> None:
    op.create_table(
        "research_findings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("researched_at", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("published", sa.String()),
        sa.Column("excerpt_kind", sa.String(), nullable=False),
        sa.Column("excerpts_json", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.Column("removed_at", sa.Integer()),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "asset_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
    )
    op.create_index("ix_research_findings_user_id", "research_findings", ["user_id"])
    op.create_index("ix_research_findings_asset_id", "research_findings", ["asset_id"])
    op.create_index(
        "ux_research_findings_active",
        "research_findings",
        ["user_id", "asset_id", "url"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.execute("ALTER TABLE research_findings ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY account_rows ON research_findings TO {ROLE} "
        f"USING (user_id = {ACCOUNT}) WITH CHECK (user_id = {ACCOUNT})"
    )


def downgrade() -> None:
    op.drop_table("research_findings")
