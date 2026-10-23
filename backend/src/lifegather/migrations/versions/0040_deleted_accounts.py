"""Deleted account ids, kept only until installation backups holding them expire.

A system table without an owner column. The per-account role used by requests
and jobs gets no access, so only the trusted system context reads or writes it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_deleted_accounts"
down_revision = "0039_email_photo_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deleted_accounts",
        sa.Column("account_id", sa.String(), primary_key=True),
        sa.Column("deleted_at", sa.Integer(), nullable=False),
        sa.Column("backups_expire_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_deleted_accounts_backups_expire_at",
        "deleted_accounts",
        ["backups_expire_at"],
    )
    # Default privileges from 0033 grant new tables to the account role.
    op.execute("REVOKE ALL ON deleted_accounts FROM lifegather_account")


def downgrade() -> None:
    op.drop_index("ix_deleted_accounts_backups_expire_at", "deleted_accounts")
    op.drop_table("deleted_accounts")
