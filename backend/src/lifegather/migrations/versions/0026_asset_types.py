"""Stable private asset type definitions and immutable revision snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0026_asset_types"
down_revision = "0025_document_formats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_types",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seed_key", sa.String()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.String(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "seed_key"),
    )
    op.create_table(
        "asset_type_fields",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("system_field", sa.String()),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.ForeignKeyConstraint(
            ["user_id", "type_id"], ["asset_types.user_id", "asset_types.id"]
        ),
    )
    op.create_table(
        "asset_type_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type_id", sa.String(), nullable=False),
        sa.Column("previous_id", sa.String()),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("definition_json", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "type_id"], ["asset_types.user_id", "asset_types.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "previous_id"],
            ["asset_type_revisions.user_id", "asset_type_revisions.id"],
        ),
    )
    for table in ("asset_types", "asset_type_fields", "asset_type_revisions"):
        op.create_index("ix_" + table + "_user_id", table, ["user_id"])
    for table in ("asset_type_fields", "asset_type_revisions"):
        op.create_index("ix_" + table + "_type_id", table, ["type_id"])


def downgrade() -> None:
    for table in ("asset_type_revisions", "asset_type_fields", "asset_types"):
        op.drop_table(table)
