"""Rename the original green dark theme to Forest dark; `dark` becomes standard."""

from alembic import op

revision = "0027_forest_dark_theme"
down_revision = "0026_asset_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_constraint("ck_user_theme", type_="check")
        batch.create_check_constraint(
            "ck_user_theme", "theme IN ('system','light','dark','forest-dark')"
        )
    op.execute("UPDATE user_settings SET theme = 'forest-dark' WHERE theme = 'dark'")


def downgrade() -> None:
    op.execute("UPDATE user_settings SET theme = 'dark' WHERE theme = 'forest-dark'")
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_constraint("ck_user_theme", type_="check")
        batch.create_check_constraint(
            "ck_user_theme", "theme IN ('system','light','dark')"
        )
