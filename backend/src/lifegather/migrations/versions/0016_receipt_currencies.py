"""Allow explicit receipt currencies while preserving every existing revision."""

import sqlalchemy as sa
from alembic import op

revision = "0016_receipt_currencies"
down_revision = "0015_receipt_details"
branch_labels = None
depends_on = None


def rebuild(currencies: str) -> None:
    checks = sa.inspect(op.get_bind()).get_check_constraints("receipt_details")
    for constraint in checks:
        if constraint["name"] and "99999999999" in constraint["sqltext"]:
            op.drop_constraint(constraint["name"], "receipt_details", type_="check")
    op.create_check_constraint(
        "ck_receipt_details_money_currency",
        "receipt_details",
        "total_minor IS NULL OR (total_minor BETWEEN 0 AND 99999999999 "
        f"AND currency IN ({currencies}))",
    )


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
