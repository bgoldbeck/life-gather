"""Link saved email sources to documents imported from their attachments."""

import sqlalchemy as sa
from alembic import op

revision = "0032_email_attachments"
down_revision = "0031_conversation_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("mailbox_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("part_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "source_id", "part_id", "document_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id"], ["documents.user_id", "documents.id"]
        ),
    )
    op.create_index("ix_email_attachments_user_id", "email_attachments", ["user_id"])
    op.create_index(
        "ix_email_attachments_document_id", "email_attachments", ["document_id"]
    )


def downgrade() -> None:
    op.drop_table("email_attachments")
