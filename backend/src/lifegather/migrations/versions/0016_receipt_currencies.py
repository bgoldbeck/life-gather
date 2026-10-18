"""Allow explicit receipt currencies while preserving every existing revision."""

import sqlalchemy as sa
from alembic import op

revision = "0016_receipt_currencies"
down_revision = "0015_receipt_details"
branch_labels = None
depends_on = None


def rebuild(currencies: str) -> None:
    table = sa.Table("receipt_details", sa.MetaData(), autoload_with=op.get_bind())
    for constraint in list(table.constraints):
        if isinstance(constraint, sa.CheckConstraint) and "99999999999" in str(
            constraint.sqltext
        ):
            table.constraints.remove(constraint)
    table.append_constraint(
        sa.CheckConstraint(
            "total_minor IS NULL OR (total_minor BETWEEN 0 AND 99999999999 "
            f"AND currency IN ({currencies}))",
            name="ck_receipt_details_money_currency",
        )
    )
    with op.batch_alter_table("receipt_details", copy_from=table, recreate="always"):
        pass


def upgrade() -> None:
    rebuild("'USD','EUR','GBP','CAD','AUD','JPY'")


def downgrade() -> None:
    count = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM receipt_details WHERE currency != 'USD'")
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError("Cannot downgrade non-USD history without data loss")
    rebuild("'USD'")
