"""Native verified email identities alongside Google, without changing user IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0005_email_auth"
down_revision = "0004_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issuer", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.UniqueConstraint("issuer", "subject"),
    )
    op.create_index(
        "ix_external_identities_user_id", "external_identities", ["user_id"]
    )
    op.execute(
        "INSERT INTO external_identities(id,user_id,issuer,subject) "
        "SELECT id,id,issuer,subject FROM users "
        "WHERE issuer='https://accounts.google.com'"
    )
    op.create_table(
        "email_credentials",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("email_key", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("generation", sa.String(), nullable=False),
        sa.Column("verified_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "email_challenges",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id")),
        sa.Column("email_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("generation", sa.String()),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.Integer()),
        sa.CheckConstraint("purpose IN ('signup','link','reset')"),
    )
    for column in ("user_id", "email_key", "expires_at"):
        op.create_index("ix_email_challenges_" + column, "email_challenges", [column])
    op.create_table(
        "auth_attempts",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_auth_attempts_expires_at", "auth_attempts", ["expires_at"])


def downgrade() -> None:
    # Downgrade disables native access; user/workspace rows are preserved.
    for table in (
        "auth_attempts",
        "email_challenges",
        "email_credentials",
        "external_identities",
    ):
        op.drop_table(table)
