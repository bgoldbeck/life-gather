"""Let an email attachment link point at a saved photo instead of a document.

Existing links keep their document. Each link names exactly one stored file.
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_email_photo_attachments"
down_revision = "0038_operational_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_attachments", sa.Column("photo_id", sa.String()))
    op.alter_column("email_attachments", "document_id", nullable=True)
    op.create_foreign_key(
        "fk_email_attachments_photo",
        "email_attachments",
        "photos",
        ["user_id", "photo_id"],
        ["user_id", "id"],
    )
    op.create_unique_constraint(
        "uq_email_attachments_photo",
        "email_attachments",
        ["user_id", "source_id", "part_id", "photo_id"],
    )
    op.create_check_constraint(
        "ck_email_attachments_one_file",
        "email_attachments",
        "(document_id IS NULL) <> (photo_id IS NULL)",
    )
    op.create_index("ix_email_attachments_photo_id", "email_attachments", ["photo_id"])


def downgrade() -> None:
    op.execute("DELETE FROM email_attachments WHERE photo_id IS NOT NULL")
    op.drop_index("ix_email_attachments_photo_id", "email_attachments")
    op.drop_constraint("ck_email_attachments_one_file", "email_attachments")
    op.drop_constraint("uq_email_attachments_photo", "email_attachments")
    op.drop_constraint("fk_email_attachments_photo", "email_attachments")
    op.alter_column("email_attachments", "document_id", nullable=False)
    op.drop_column("email_attachments", "photo_id")
