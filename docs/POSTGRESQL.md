# PostgreSQL database

LifeGather stores all records, sign-in sessions, encrypted credentials and
original photo/document bytes in PostgreSQL. Releases up to 0.74 used a SQLite
file at `/data/auth.sqlite3`; that storage has been removed. The `vector`
(pgvector) extension is enabled so embeddings can later live next to the records
they describe; nothing uses it yet.

## What the app needs

| Setting | Value |
| --- | --- |
| `LIFEGATHER_DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/DATABASE` (required) |
| PostgreSQL | 16 or later with the pgvector extension available (the Compose files use `pgvector/pgvector:pg17`) |
| Collation | `C` (byte order). The app refuses to start on a locale collation so ordering and paging never depend on the server's locale. |
| `/data` | Still mounted. It holds the original photo/document files (`/data/files`, see [file storage](FILE_STORAGE.md)), the old SQLite file during the one-time import, and the operator recovery staging area. |

Use letters and digits for the password, or percent-encode other characters in
the URL. The app runs its migrations on startup inside one transaction.

The Compose files in this repository add a `db` service. Set
`LIFEGATHER_DB_PASSWORD` once (for example in `.env` next to the Compose file, or
in the TrueNAS app's environment), and keep it: it becomes the database
password the first time the `lifegather-db` volume is created.

```sh
echo "LIFEGATHER_DB_PASSWORD=$(openssl rand -hex 24)" >> .env
docker compose up -d --wait
```

The database container publishes no ports; only the LifeGather container talks
to it. Never remove the `lifegather-db` volume: it is now where your records live.

### Using an existing PostgreSQL server

Create a dedicated database with byte-order collation and allow the extension:

```sql
CREATE ROLE lifegather LOGIN PASSWORD 'letters-and-digits';
-- Row-level security role used while acting for one account (0.81.0+).
CREATE ROLE lifegather_account NOLOGIN NOINHERIT;
GRANT lifegather_account TO lifegather;
CREATE DATABASE lifegather OWNER lifegather TEMPLATE template0
  ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';
\c lifegather
CREATE EXTENSION IF NOT EXISTS vector;
```

Creating the extension and the `lifegather_account` role needs a superuser once;
the migrations then find them. See [account isolation](ACCOUNT_ISOLATION.md).

## Moving an existing SQLite installation

The first start against an **empty** PostgreSQL database copies
`/data/auth.sqlite3` automatically:

1. Take an encrypted backup with the old release
   ([operator recovery](OPERATOR_RECOVERY.md)), and make sure the old app has been
   updated to 0.74 and started at least once.
2. Stop the old app.
3. Update the Compose/TrueNAS app definition to the new files (adds the `db`
   service, `LIFEGATHER_DB_PASSWORD` and `LIFEGATHER_DATABASE_URL`). Keep the
   same `/data` mount.
4. Start it. The log shows `Imported N rows from /data/auth.sqlite3 into
   PostgreSQL`. Sign in and check your items, photos and documents.

The import runs in one PostgreSQL transaction, checks SQLite integrity first,
compares every table's row count, and rebuilds the search index. If anything
fails nothing is kept in PostgreSQL and the app does not start; fix the cause and
start again. The SQLite file is opened read-only and never changed or deleted.
Once PostgreSQL has a LifeGather schema the file is ignored; delete it after you
have checked the data and taken a new backup.

To run the import by hand instead (for example against an external server):

```sh
docker compose run --rm backend python -m lifegather.legacy_import /data/auth.sqlite3
```

## Backups

`python -m lifegather.recovery backup` now captures a consistent logical
snapshot of the whole database (format `lifegather-recovery/2`). Restores load
into a new, empty PostgreSQL database named by `LIFEGATHER_DATABASE_URL`.
Bundles made by SQLite releases can still be verified and restored; the restore
imports them into PostgreSQL the same way. See [operator recovery](OPERATOR_RECOVERY.md).

Ordinary PostgreSQL tools (`pg_dump`, volume snapshots of a stopped database)
also work, but the encrypted bundle is the only backup that also carries the
installation configuration and vault key.

## Tests

The Windows publisher now runs the complete backend suite inside Linux, split
into four bounded shards. Each shard has its own PostgreSQL17 server and private
network; no test database port is published. This avoids repeated Windows-to-
Docker database round trips while preserving account and per-test isolation.

Run the same verification directly from the repository root:

```sh
uv run --project backend --locked python scripts/run_backend_tests.py
# Lower concurrency on a smaller machine:
uv run --project backend --locked python scripts/run_backend_tests.py --workers 2
```

The first run builds the locked test image; later runs reuse dependency layers.
The runner collects the suite once, assigns every whole file exactly once,
checks each shard's expected collection count, and refuses success on failures
or changing input files. It prints elapsed progress every15 seconds. Ignored
`test-results/backend-*/` contains the input fingerprint, image ID, allocation,
total/count checks, per-shard logs and JUnit reports. Each log includes the
slowest25 test phases. Build time is included in the final wall-time report.
Ctrl+C stops verification and cleans only that run's test containers/networks;
the publisher must not build/upload after a failed or canceled shard. Abruptly
killing the terminal/process can prevent cleanup; identify leftovers by the
`lifegather.test-run` Docker label and exact invocation ID before removing them.

For targeted development tests, a host PostgreSQL server can still be used as
described below. Keep full verification for release; use a focused test file or
`-k` selection while working on one behavior. Add `--durations=25` to inspect
slow setup/call/teardown phases.

Pure schema/date/validation tests do not need PostgreSQL. Environment cleanup
remains automatic, but app/HTTP modules opt into `configured_database` with
`pytestmark = pytest.mark.usefixtures("configured_database")`; shared app
fixtures declare `configured_database: str` explicitly so importing tests inherit
the dependency. Service-only modules call `database_support.database(path)`
directly. Mixed HTTP/service modules retain module-level opt-in; the timing
reports can guide finer fixture splitting without sharing mutable state.
The migrated template starts lazily on the first actual database request.
Do not point test configuration at a personal/application database or share
mutable accounts between tests to improve timing.

The backend tests need PostgreSQL with pgvector. Set
`LIFEGATHER_TEST_DATABASE_URL` to a server URL whose user may create databases,
for example a throwaway container:

```sh
docker run -d --name lifegather-test-db -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 pgvector/pgvector:pg17
export LIFEGATHER_TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres
cd backend && uv run pytest
```

Without the variable, the suite starts a private temporary cluster when
PostgreSQL's `initdb` is installed and tests run as a non-root user. Each test
gets its own database, cloned from a migrated template and dropped afterwards.
