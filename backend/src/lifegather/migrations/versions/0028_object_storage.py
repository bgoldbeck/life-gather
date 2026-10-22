"""Original document/photo bytes move to object storage; rows keep their keys."""

import sqlalchemy as sa
from alembic import op

revision = "0028_object_storage"
down_revision = "0027_forest_dark_theme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing BLOB columns stay; the app copies their bytes to storage on startup
    # and clears them only after the stored copy is verified.
    op.add_column("documents", sa.Column("original_key", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("original_key", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("preview_key", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    stored = bind.execute(
        sa.text(
            "SELECT 1 FROM documents WHERE original_key IS NOT NULL UNION ALL "
            "SELECT 1 FROM photos WHERE original_key IS NOT NULL "
            "OR preview_key IS NOT NULL LIMIT 1"
        )
    ).first()
    if stored is not None:
        raise RuntimeError(
            "Downgrade refused while original files live in object storage"
        )
    with op.batch_alter_table("photos") as batch:
        batch.drop_column("preview_key")
        batch.drop_column("original_key")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("original_key")
