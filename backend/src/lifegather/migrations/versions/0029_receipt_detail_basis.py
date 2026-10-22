"""Record whether each receipt detail revision used labeled or reviewed text."""

import sqlalchemy as sa
from alembic import op

revision = "0029_receipt_detail_basis"
down_revision = "0028_object_storage"
branch_labels = None
depends_on = None
CHECK = "ck_receipt_details_basis"


def upgrade() -> None:
    # Every existing revision was saved under the strict labeled-passage rule.
    op.add_column(
        "receipt_details",
        sa.Column("basis", sa.String(), nullable=False, server_default="labeled"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            CHECK, "receipt_details", "basis IN ('labeled','reviewed')"
        )
        return
    # SQLite cannot add a constraint in place. Rebuild from the reflected table
    # so the existing unnamed money/index checks are kept, as 0016 does.
    table = sa.Table("receipt_details", sa.MetaData(), autoload_with=op.get_bind())
    table.append_constraint(
        sa.CheckConstraint("basis IN ('labeled','reviewed')", name=CHECK)
    )
    with op.batch_alter_table("receipt_details", copy_from=table, recreate="always"):
        pass


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
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(CHECK, "receipt_details", type_="check")
        op.drop_column("receipt_details", "basis")
        return
    table = sa.Table("receipt_details", sa.MetaData(), autoload_with=op.get_bind())
    for constraint in list(table.constraints):
        if isinstance(constraint, sa.CheckConstraint) and "basis" in str(
            constraint.sqltext
        ):
            table.constraints.remove(constraint)
    with op.batch_alter_table(
        "receipt_details", copy_from=table, recreate="always"
    ) as batch:
        batch.drop_column("basis")
