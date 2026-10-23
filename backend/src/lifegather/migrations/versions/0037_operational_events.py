"""Counted installation problems for the operator view and alerts.

A system table without an owner column. The per-account role used by requests
and jobs gets no access, so only the trusted system context reads or writes it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_operational_events"
down_revision = "0036_credential_auth_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_events",
        sa.Column("fingerprint", sa.String(), primary_key=True),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("logger", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("detail_json", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_at", sa.Integer(), nullable=False),
        sa.Column("last_at", sa.Integer(), nullable=False),
        sa.Column("alerted_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("level IN ('error','critical')"),
    )
    op.create_index("ix_operational_events_last_at", "operational_events", ["last_at"])
    # Default privileges from 0033 grant new tables to the account role.
    op.execute("REVOKE ALL ON operational_events FROM lifegather_account")


def downgrade() -> None:
    op.drop_index("ix_operational_events_last_at", "operational_events")
    op.drop_table("operational_events")
