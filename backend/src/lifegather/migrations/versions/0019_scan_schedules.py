"""Private calendar schedules, dispatched atomically into existing scan runs."""

import sqlalchemy as sa
from alembic import op

revision = "0019_scan_schedules"
down_revision = "0018_modular_scans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "request_id",
                "fingerprint",
                "label",
                "handler_key",
                "config_json",
                "timezone",
                "cadence",
                "local_time",
                "last_status",
            )
        ],
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in (
                "weekday",
                "lookback_days",
                "revision",
                "next_run",
                "created_at",
                "updated_at",
            )
        ],
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_due", sa.Integer()),
        sa.Column("last_run_id", sa.String()),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "last_run_id"], ["scan_runs.user_id", "scan_runs.id"]
        ),
        sa.CheckConstraint("cadence IN ('daily','weekly')"),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6 AND lookback_days BETWEEN 1 AND 30"
        ),
    )
    op.create_index("ix_scan_schedules_user_id", "scan_schedules", ["user_id"])
    op.create_index("ix_scan_schedules_due", "scan_schedules", ["enabled", "next_run"])


def downgrade() -> None:
    op.drop_table("scan_schedules")
