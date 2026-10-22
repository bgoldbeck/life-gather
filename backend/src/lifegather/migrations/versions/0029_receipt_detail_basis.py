"""Record whether each receipt detail revision used labeled or reviewed text."""

import sqlalchemy as sa
from alembic import op

revision = "0029_receipt_detail_basis"
down_revision = "0028_object_storage"
branch_labels = None
depends_on = None
CHECK = "ck_receipt_details_basis"
ALLOWED = "basis IN ('labeled','reviewed')"


def upgrade() -> None:
    # Every existing revision was saved under the strict labeled-passage rule.
    if op.get_bind().dialect.name == "sqlite":
        # An in-place column with its own CHECK avoids rebuilding the table,
        # which keeps the existing unnamed money/index checks untouched.
        op.execute(
            "ALTER TABLE receipt_details ADD COLUMN basis VARCHAR NOT NULL "
            f"DEFAULT 'labeled' CONSTRAINT {CHECK} CHECK ({ALLOWED})"
        )
        return
    op.add_column(
        "receipt_details",
        sa.Column("basis", sa.String(), nullable=False, server_default="labeled"),
    )
    op.create_check_constraint(CHECK, "receipt_details", ALLOWED)


def downgrade() -> None:
    reviewed = (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM receipt_details WHERE basis != 'labeled'"))
        .first()
    )
    if reviewed is not None:
        raise RuntimeError(
            "Downgrade refused: reviewed receipt details would lose their basis"
        )
    if op.get_bind().dialect.name == "sqlite":
        # pysqlite opens its implicit transaction only before DML. Start it
        # here so the drop is rolled back if an older downgrade then refuses.
        op.execute("UPDATE receipt_details SET basis = basis WHERE 0 = 1")
        op.execute("ALTER TABLE receipt_details DROP COLUMN basis")
        return
    op.drop_constraint(CHECK, "receipt_details", type_="check")
    op.drop_column("receipt_details", "basis")
