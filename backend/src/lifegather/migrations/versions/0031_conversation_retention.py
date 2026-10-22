"""Per-account chat conversation retention; NULL keeps conversations forever."""

import sqlalchemy as sa
from alembic import op

revision = "0031_conversation_retention"
down_revision = "0030_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "conversation_retention_days",
            sa.Integer(),
            sa.CheckConstraint(
                "conversation_retention_days IS NULL "
                "OR conversation_retention_days IN (30, 90, 365)",
                name="ck_user_conversation_retention",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "conversation_retention_days")
