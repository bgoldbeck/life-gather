"""Row-level security as a second lock on every account-owned table.

The application connects as the database owner (or a superuser) and stays
unrestricted for startup, migrations and background dispatch. While a request
or job acts for one account, its connections switch to `lifegather_account`,
which these policies limit to rows owned by `lifegather.account_id`.
"""

from alembic import op

revision = "0033_account_row_security"
down_revision = "0032_email_attachments"
branch_labels = None
depends_on = None

ROLE = "lifegather_account"
ACCOUNT = "current_setting('lifegather.account_id', true)"

# Every table with a user_id column at this revision. New owned tables must add
# their own policy; tests/test_account_isolation.py fails until they do.
OWNED = (
    "asset_actions",
    "asset_consolidation_members",
    "asset_consolidations",
    "asset_proposals",
    "asset_type_fields",
    "asset_type_revisions",
    "asset_types",
    "chat_conversations",
    "chat_preferences",
    "chat_turns",
    "chat_usage",
    "credentials",
    "documents",
    "email_attachments",
    "email_challenges",
    "email_credentials",
    "email_discoveries",
    "external_identities",
    "login_sessions",
    "mailbox_oauth_flows",
    "mailboxes",
    "maintenance_revisions",
    "maintenance_tasks",
    "memory_aliases",
    "memory_audit",
    "memory_entities",
    "memory_evidence",
    "memory_facts",
    "memory_fts",
    "memory_note_revisions",
    "memory_sources",
    "photo_assets",
    "photos",
    "purchase_evidence",
    "receipt_details",
    "receipt_proposals",
    "reconciliation_bindings",
    "reconciliation_candidates",
    "reconciliation_decisions",
    "reconciliation_lines",
    "reconciliation_observations",
    "reconciliation_purchases",
    "scan_run_items",
    "scan_runs",
    "scan_schedules",
    "user_settings",
)


def upgrade() -> None:
    # Roles are shared by every database on the server; create it once.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN NOINHERIT;
            END IF;
        EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
        END
        $$
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT pg_has_role(current_user, '{ROLE}', 'MEMBER') THEN
                EXECUTE format('GRANT {ROLE} TO %I', current_user);
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {ROLE}")
    # Tables added by later migrations (run by the same owner) are reachable too.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {ROLE}"
    )
    for table, column in (*((name, "user_id") for name in OWNED), ("users", "id")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY account_rows ON {table} TO {ROLE} "
            f"USING ({column} = {ACCOUNT}) WITH CHECK ({column} = {ACCOUNT})"
        )


def downgrade() -> None:
    for table in (*OWNED, "users"):
        op.execute(f"DROP POLICY IF EXISTS account_rows ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    # The role is shared by other databases on the server, so it stays.
