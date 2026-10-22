"""Durable owned scan runs and atomic evidence checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "0018_modular_scans"
down_revision = "0017_private_mailboxes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "handler_key",
                "resource_key",
                "config_json",
                "cursor_json",
                "request_id",
                "fingerprint",
                "state",
            )
        ],
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in (
                "scanned",
                "imported",
                "existing",
                "skipped",
                "steps",
                "attempts",
                "created_at",
                "updated_at",
            )
        ],
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String()),
        sa.Column("lease_token", sa.String()),
        *[
            sa.Column(name, sa.Integer())
            for name in (
                "lease_until",
                "started_at",
                "completed_at",
            )
        ],
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','canceled')"
        ),
        sa.CheckConstraint("scanned BETWEEN 0 AND 50 AND steps BETWEEN 0 AND 100"),
    )
    op.create_index("ix_scan_runs_user_id", "scan_runs", ["user_id"])
    op.create_index("ix_scan_runs_state", "scan_runs", ["state"])
    op.create_index(
        "uq_active_scan_resource",
        "scan_runs",
        ["user_id", "resource_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued','running')"),
    )
    op.create_table(
        "scan_run_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String()),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "item_key",
                "label",
                "state",
                "reason",
                "metadata_json",
            )
        ],
        sa.UniqueConstraint("user_id", "run_id", "item_key"),
        sa.UniqueConstraint("user_id", "run_id", "sequence"),
        sa.ForeignKeyConstraint(
            ["user_id", "run_id"], ["scan_runs.user_id", "scan_runs.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
    )
    op.create_index("ix_scan_run_items_user_id", "scan_run_items", ["user_id"])
    op.create_index("ix_scan_run_items_run_id", "scan_run_items", ["run_id"])


def downgrade() -> None:
    op.drop_table("scan_run_items")
    op.drop_table("scan_runs")
