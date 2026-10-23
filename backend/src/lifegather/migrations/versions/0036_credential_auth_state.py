"""Remember whether a saved credential's provider last accepted or refused it."""

import sqlalchemy as sa
from alembic import op

revision = "0036_credential_auth_state"
down_revision = "0035_research_save_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("credentials", sa.Column("auth_state", sa.String(), nullable=True))
    op.add_column(
        "credentials", sa.Column("auth_checked_at", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_credentials_auth_state",
        "credentials",
        "auth_state IS NULL OR auth_state IN ('working', 'reconnect')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_credentials_auth_state", "credentials", type_="check")
    op.drop_column("credentials", "auth_checked_at")
    op.drop_column("credentials", "auth_state")
