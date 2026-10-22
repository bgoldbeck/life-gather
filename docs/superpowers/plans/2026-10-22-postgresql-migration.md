# PostgreSQL storage migration

Requested 2026-10-22: replace SQLite with PostgreSQL everywhere and remove SQLite
as the application database, with a one-time path for existing installations.

## Scope

1. **Configuration.** New required `LIFEGATHER_DATABASE_URL`
   (`postgresql+psycopg://user:password@host:5432/db`). `psycopg` 3 is the driver.
2. **Schema history.** Keep the existing Alembic revisions and IDs; make them
   create the same schema on PostgreSQL (partial indexes use `postgresql_where`,
   the FTS5 table becomes a `tsvector` table with a GIN index). No new revision
   is needed because the schema is equivalent; the head stays `0027_forest_dark_theme`.
3. **Services.** Replace SQLite-only SQL: dialect `insert ... on conflict`,
   `json_extract`, FTS `MATCH`, `rowid`/`blobopen`, and the explicit
   `BEGIN`/`BEGIN IMMEDIATE` transaction modes. Snapshot reads use
   `REPEATABLE READ`; serialized writers take a transaction advisory lock, which
   keeps SQLite's single-writer guarantees.
4. **One-time import.** `python -m lifegather.legacy_import` copies an existing
   `/data/auth.sqlite3` (at the last SQLite schema, `0027_forest_dark_theme`) into
   an empty PostgreSQL database inside one transaction, verifies row counts and
   rebuilds search. The app runs the same import automatically on startup when
   PostgreSQL is empty and the legacy file exists. The SQLite file is never
   modified or deleted.
5. **Encrypted recovery.** The bundle's database part becomes a portable logical
   snapshot (`database.jsonl`, format `lifegather-recovery/2`) taken in one
   `REPEATABLE READ` transaction. Verification still checks vault identity,
   credentials and original hashes without a database. Restore writes the config
   and key to a fresh directory and loads the snapshot into an empty PostgreSQL
   database given with `--database-url`.
6. **Deployment.** Compose files gain a `db` PostgreSQL service with its own
   persistent volume, a health check and `LIFEGATHER_DB_PASSWORD`; TrueNAS,
   local release and recovery docs are updated. Release/test-login scripts run a
   PostgreSQL sidecar.
7. **Tests.** Every test runs against PostgreSQL. `LIFEGATHER_TEST_DATABASE_URL`
   selects a server; otherwise the suite starts a throwaway local cluster when
   `initdb` is available. Each test gets its own database cloned from a migrated
   template.

## Acceptance checks

- `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`
  pass from `backend/` against PostgreSQL.
- An SQLite database created by the previous release imports with identical row
  counts, working search, sign-in and originals.
- `rg -i sqlite backend/src` only finds the legacy importer.
- `docker compose config` validates both compose files.

## Out of scope

Schema redesign, new features, Docker image publication from this cloud session.
