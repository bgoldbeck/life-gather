"""Private PDF originals and reviewed text provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0013_private_documents"
down_revision = "0012_chat_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.String(), nullable=False),
        sa.Column("text_truncated", sa.Boolean(), nullable=False),
        sa.Column("original", sa.LargeBinary(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.Integer(), nullable=True),
        sa.UniqueConstraint("user_id", "id"),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index(
        "uq_documents_active_hash",
        "documents",
        ["user_id", "content_hash"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("documents")
