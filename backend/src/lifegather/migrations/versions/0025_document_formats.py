"""Retain document format and parser provenance; existing documents remain PDFs."""

import sqlalchemy as sa
from alembic import op

revision = "0025_document_formats"
down_revision = "0024_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("format", sa.String(), nullable=False, server_default="pdf"),
    )
    op.add_column(
        "documents",
        sa.Column(
            "extraction_metadata", sa.String(), nullable=False, server_default="{}"
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT COUNT(*) FROM documents WHERE format != 'pdf'")
    ).scalar():
        raise ValueError("Cannot downgrade while non-PDF documents exist")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("extraction_metadata")
        batch.drop_column("format")
