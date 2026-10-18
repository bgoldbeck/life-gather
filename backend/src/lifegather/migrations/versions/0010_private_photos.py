"""Private originals, sanitized previews and explicit asset attachments."""

import sqlalchemy as sa
from alembic import op

revision = "0010_private_photos"
down_revision = "0009_asset_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(n, sa.String(), nullable=False)
            for n in ("content_hash", "filename", "mime", "purpose")
        ],
        *[
            sa.Column(n, sa.Integer(), nullable=False)
            for n in (
                "size",
                "width",
                "height",
                "preview_size",
                "created_at",
                "updated_at",
            )
        ],
        sa.Column("deleted_at", sa.Integer(), nullable=True),
        sa.Column("original", sa.LargeBinary(), nullable=True),
        sa.Column("preview", sa.LargeBinary(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.UniqueConstraint("user_id", "id"),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    op.create_index("ix_photos_user_id", "photos", ["user_id"])
    op.create_index(
        "uq_photos_active_hash",
        "photos",
        ["user_id", "content_hash"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "photo_assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("photo_id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "photo_id", "asset_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "photo_id"], ["photos.user_id", "photos.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "asset_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
    )
    for column in ("user_id", "photo_id", "asset_id"):
        op.create_index("ix_photo_assets_" + column, "photo_assets", [column])


def downgrade() -> None:
    op.drop_table("photo_assets")
    op.drop_table("photos")
