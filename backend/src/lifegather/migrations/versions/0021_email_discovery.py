"""Cache completed email extraction, including empty findings."""

import sqlalchemy as sa
from alembic import op

revision = "0021_email_discovery"
down_revision = "0020_purchase_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_discoveries",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("result_json", sa.String(), nullable=False),
        sa.Column("extraction_json", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )


def downgrade() -> None:
    op.drop_table("email_discoveries")
