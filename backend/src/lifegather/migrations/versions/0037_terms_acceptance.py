"""Record which terms-of-use version each account accepted, and when."""

import sqlalchemy as sa
from alembic import op

revision = "0037_terms_acceptance"
down_revision = "0036_credential_auth_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_version", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("terms_accepted_at", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
