"""Keep workflow attribution on existing audit events without guessing older data."""

import sqlalchemy as sa
from alembic import op

revision = "0022_change_origins"
down_revision = "0021_email_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_audit", sa.Column("provenance_json", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_audit_owned_target", "memory_audit", ["user_id", "target_id", "operation"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_owned_target", table_name="memory_audit")
    op.drop_column("memory_audit", "provenance_json")
