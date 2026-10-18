"""Per-user appearance without changing existing external-AI consent."""

import sqlalchemy as sa
from alembic import op

revision = "0011_appearance"
down_revision = "0010_private_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(
            sa.Column("theme", sa.String(), nullable=False, server_default="system")
        )
        batch.create_check_constraint(
            "ck_user_theme", "theme IN ('system','light','dark')"
        )


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_constraint("ck_user_theme", type_="check")
        batch.drop_column("theme")
