"""Enable pgvector so embeddings can live next to the records they describe."""

from alembic import op

revision = "0030_pgvector"
down_revision = "0029_receipt_detail_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
