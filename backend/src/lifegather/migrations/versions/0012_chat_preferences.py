"""Private explicit chat choices; no AI consent changes."""

import sqlalchemy as sa
from alembic import op

revision = "0012_chat_preferences"
down_revision = "0011_appearance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_preferences",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "credential_id",
            sa.String(),
            sa.ForeignKey("credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("chat_preferences")
