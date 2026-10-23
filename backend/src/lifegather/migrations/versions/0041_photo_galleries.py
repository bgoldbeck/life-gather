"""Owner-named photo galleries, such as one event, and the photos in each."""

import sqlalchemy as sa
from alembic import op

revision = "0041_photo_galleries"
down_revision = "0040_deleted_accounts"
branch_labels = None
depends_on = None

ROLE = "lifegather_account"
ACCOUNT = "current_setting('lifegather.account_id', true)"


def upgrade() -> None:
    op.create_table(
        "photo_galleries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("event_on", sa.String()),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
    )
    op.create_index("ix_photo_galleries_user_id", "photo_galleries", ["user_id"])
    op.create_table(
        "photo_gallery_photos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("gallery_id", sa.String(), nullable=False),
        sa.Column("photo_id", sa.String(), nullable=False),
        sa.Column("added_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "gallery_id", "photo_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "gallery_id"],
            ["photo_galleries.user_id", "photo_galleries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "photo_id"], ["photos.user_id", "photos.id"]
        ),
    )
    for column in ("user_id", "gallery_id", "photo_id"):
        op.create_index(
            "ix_photo_gallery_photos_" + column, "photo_gallery_photos", [column]
        )
    for table in ("photo_galleries", "photo_gallery_photos"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY account_rows ON {table} TO {ROLE} "
            f"USING (user_id = {ACCOUNT}) WITH CHECK (user_id = {ACCOUNT})"
        )


def downgrade() -> None:
    op.drop_table("photo_gallery_photos")
    op.drop_table("photo_galleries")
