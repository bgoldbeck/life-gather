# Portable container (Phase 5.1)

Requested 2026-10-22: build feature-plan increment 5.1 so one image runs both
self-hosted (Docker Compose on Linux, unchanged default) and later on a hosted
container platform. Design: [hosted SaaS report](../../HOSTED_SAAS_CLOUDFLARE.md),
Step A. Builds on the PostgreSQL migration; no Cloudflare deploy code (that is 5.4).

## Scope

1. **Image extras.** The runtime image installs the `s3` extra (boto3) so
   `LIFEGATHER_STORAGE_BACKEND=s3` works from the published image. The Postgres
   driver comes with the PostgreSQL migration.
2. **Vault keys from the environment, with key IDs.** `LIFEGATHER_VAULT_KEYS`
   takes `id:base64key[,id:base64key...]`; the first is active, the rest are
   previous keys. The existing `LIFEGATHER_VAULT_KEY_FILE` keeps working alone, and
   with `LIFEGATHER_VAULT_KEYS` set it counts as previous key `file`. When the
   database is still encrypted under a previous key, the startup job re-encrypts
   every stored credential under the active key in one transaction and records
   the new fingerprint. Instances still holding an old key refuse to write.
3. **Startup job.** `python -m lifegather.migrate` runs the one-time SQLite import,
   Alembic upgrade, inline-file moves and vault rotation under a PostgreSQL
   session advisory lock, so several instances never race. By default the app
   still runs the same job at startup (self-hosting unchanged);
   `LIFEGATHER_MIGRATE_ON_START=false` leaves it to the one-shot job and the app
   refuses to start on an outdated schema.
4. **Liveness and readiness.** `/health` stays the process liveness check used by
   Docker. New `/health/ready` returns 200 only when the database answers and its
   schema is at the application's head revision, else 503. No account details.
5. **Trusted proxies.** `LIFEGATHER_TRUSTED_PROXIES` (IP addresses or CIDR
   networks, empty by default) enables forwarded client IP and scheme from those
   peers only. Login rate limits then see the real client. Default stays off.

## Acceptance checks

- `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`
  pass from `backend/`.
- Tests: env keyring parsing and validation; rotation re-encrypts and old
  instances refuse writes; two concurrent startup jobs serialize; readiness 200/503;
  forwarded headers honored only from trusted peers; `uv sync --locked --extra s3`.
- `docker compose config` still validates; default Compose behaviour unchanged.

## Out of scope

External background mode (5.2), row-level security (5.3), Cloudflare files (5.4),
Docker image build/publication from this cloud session.
