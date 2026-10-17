"""Owner-scoped preferences and encrypted credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0002_private_settings"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vault_key",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("allow_external_ai", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_credentials_user_id", "credentials", ["user_id"])


def downgrade() -> None:
    op.drop_table("credentials")
    op.drop_table("user_settings")
    op.drop_table("vault_key")
