"""Owner-bound Gmail grants and one-time session-bound consent flows."""

import sqlalchemy as sa
from alembic import op

revision = "0017_private_mailboxes"
down_revision = "0016_receipt_currencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_credentials_user_id_id", "credentials", ["user_id", "id"], unique=True
    )
    op.create_table(
        "mailboxes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "credential_id",
            sa.String(),
            sa.ForeignKey("credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("account_key", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "account_key"),
        sa.ForeignKeyConstraint(
            ["user_id", "credential_id"], ["credentials.user_id", "credentials.id"]
        ),
    )
    op.create_index("ix_mailboxes_user_id", "mailboxes", ["user_id"])
    op.create_table(
        "mailbox_oauth_flows",
        sa.Column("state_hash", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(), nullable=False),
        sa.Column("browser_hash", sa.String(), nullable=False),
        sa.Column("verifier", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_mailbox_oauth_flows_user_id", "mailbox_oauth_flows", ["user_id"]
    )
    op.create_index(
        "ix_mailbox_oauth_flows_expires_at", "mailbox_oauth_flows", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("mailbox_oauth_flows")
    op.drop_table("mailboxes")
    op.drop_index("uq_credentials_user_id_id", table_name="credentials")
