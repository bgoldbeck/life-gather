"""Private maintenance tasks and sourced immutable revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0024_maintenance"
down_revision = "0023_asset_consolidation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in ("entity_id", "source_id", "request_id", "fingerprint")
        ],
        sa.Column("recorded_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        *[
            sa.ForeignKeyConstraint(
                ["user_id", field], [table + ".user_id", table + ".id"]
            )
            for field, table in (
                ("entity_id", "memory_entities"),
                ("source_id", "memory_sources"),
            )
        ],
    )
    op.create_index("ix_maintenance_tasks_user_id", "maintenance_tasks", ["user_id"])
    op.create_index(
        "ix_maintenance_tasks_entity_id", "maintenance_tasks", ["entity_id"]
    )
    op.create_table(
        "maintenance_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "task_id",
                "title",
                "timezone",
                "state",
                "source_id",
                "request_id",
                "fingerprint",
            )
        ],
        sa.Column("previous_id", sa.String()),
        sa.Column("due_on", sa.Date()),
        sa.Column("completed_on", sa.Date()),
        sa.Column("recorded_at", sa.BigInteger(), nullable=False),
        sa.Column("superseded_at", sa.BigInteger()),
        sa.UniqueConstraint("user_id", "id"),
        sa.UniqueConstraint("user_id", "task_id", "id"),
        sa.UniqueConstraint("user_id", "request_id"),
        sa.UniqueConstraint("user_id", "previous_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "task_id"],
            ["maintenance_tasks.user_id", "maintenance_tasks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"], ["memory_sources.user_id", "memory_sources.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "task_id", "previous_id"],
            [
                "maintenance_revisions.user_id",
                "maintenance_revisions.task_id",
                "maintenance_revisions.id",
            ],
        ),
        sa.CheckConstraint(
            "state IN ('open','completed','canceled')", name="ck_maintenance_state"
        ),
        sa.CheckConstraint(
            "completed_on IS NULL OR state = 'completed'",
            name="ck_maintenance_completion",
        ),
        sa.CheckConstraint(
            "superseded_at IS NULL OR superseded_at > recorded_at",
            name="ck_maintenance_revision_time",
        ),
    )
    op.create_index(
        "ix_maintenance_revisions_user_id", "maintenance_revisions", ["user_id"]
    )
    op.create_index(
        "ix_maintenance_current",
        "maintenance_revisions",
        ["user_id", "task_id"],
        unique=True,
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_maintenance_due",
        "maintenance_revisions",
        ["user_id", "state", "superseded_at", "due_on"],
    )


def downgrade() -> None:
    op.drop_table("maintenance_revisions")
    op.drop_table("maintenance_tasks")
