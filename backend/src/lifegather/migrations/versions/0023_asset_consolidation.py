"""Owner-constrained reversible two-record physical identity choices."""

import sqlalchemy as sa
from alembic import op

revision = "0023_asset_consolidation"
down_revision = "0022_change_origins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_consolidations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "primary_id",
                "secondary_id",
                "source_id",
                "request_id",
                "fingerprint",
                "state_token",
            )
        ],
        sa.Column("recorded_at", sa.BigInteger(), nullable=False),
        sa.Column("superseded_at", sa.BigInteger()),
        *[
            sa.Column(name, sa.String())
            for name in (
                "reverse_source_id",
                "reverse_request_id",
                "reverse_fingerprint",
            )
        ],
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.UniqueConstraint("user_id", "reverse_request_id"),
        sa.CheckConstraint("primary_id != secondary_id", name="ck_consolidation_pair"),
        sa.CheckConstraint(
            "superseded_at IS NULL OR superseded_at > recorded_at",
            name="ck_consolidation_time",
        ),
        *[
            sa.ForeignKeyConstraint(
                ["user_id", field], [table + ".user_id", table + ".id"]
            )
            for field, table in (
                ("primary_id", "memory_entities"),
                ("secondary_id", "memory_entities"),
                ("source_id", "memory_sources"),
                ("reverse_source_id", "memory_sources"),
            )
        ],
    )
    op.create_index(
        "ix_asset_consolidations_user_id", "asset_consolidations", ["user_id"]
    )
    op.create_table(
        "asset_consolidation_members",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("entity_id", sa.String(), primary_key=True),
        sa.Column("consolidation_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "entity_id"], ["memory_entities.user_id", "memory_entities.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "consolidation_id"],
            ["asset_consolidations.user_id", "asset_consolidations.id"],
        ),
    )
    op.create_index(
        "ix_asset_consolidation_members_consolidation_id",
        "asset_consolidation_members",
        ["consolidation_id"],
    )


def downgrade() -> None:
    op.drop_table("asset_consolidation_members")
    op.drop_table("asset_consolidations")
