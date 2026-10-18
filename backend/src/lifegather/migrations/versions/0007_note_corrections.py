"""Append-only saved-note history without replacing original source evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0007_note_corrections"
down_revision = "0006_text_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_note_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("root_source_id", sa.String(), nullable=False),
        sa.Column("previous_source_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.UniqueConstraint("user_id", "previous_source_id"),
        sa.UniqueConstraint("user_id", "source_id"),
        sa.CheckConstraint(
            "source_id != previous_source_id AND source_id != root_source_id"
        ),
        *[
            sa.ForeignKeyConstraint(
                ["user_id", column], ["memory_sources.user_id", "memory_sources.id"]
            )
            for column in ("root_source_id", "previous_source_id", "source_id")
        ],
    )
    for column in ("user_id", "root_source_id"):
        op.create_index(
            "ix_memory_note_revisions_" + column, "memory_note_revisions", [column]
        )


def downgrade() -> None:
    # Correction sources remain preserved as originals; only version links are removed.
    op.drop_table("memory_note_revisions")
