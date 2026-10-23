# Cloudflare test site package (Phase 5.4, staging only)

Requested 2026-10-23. Builds `deploy/cloudflare/` so Lisa can run a private test
copy of LifeGather on Cloudflare. Not a public launch: the Phase 3 gate, Google
verification (5.7) and hosted sign-up checks (5.5, another branch) come first.

## Scope

- Worker `lifegather-test` with a Container class running the unchanged image
  (built from the repository `Dockerfile`), Postgres and R2 settings passed from
  Worker secrets, `LIFEGATHER_BACKGROUND_MODE=external`.
- Edge rules: requests require a valid Cloudflare Access token for the test site
  (refuses to serve until Access is configured), `/internal/*` is never reachable
  from outside, `X-Forwarded-For`/`-Proto` are overwritten from Cloudflare's view.
- Cron Trigger calls `POST /internal/jobs/tick` with the tick token.
- Runbook `docs/CLOUDFLARE_TEST_SITE.md`: every step Lisa does in her Cloudflare,
  Neon (or other Postgres) and Google accounts, plus checks and teardown.
- No Python app changes expected; Cloudflare code stays in `deploy/cloudflare/`.

## Acceptance checks

- `npm run check` in `deploy/cloudflare/` (TypeScript strict + unit tests for
  routing, header rewriting, Access verification, env mapping, tick request).
- `wrangler deploy --dry-run` validates the config and bundles the Worker.
- A backend test proves every container setting the Worker passes is a real
  `Settings` field, so a rename breaks the build instead of the test site.
- Full backend suite on PostgreSQL and frontend checks still pass.
- Live deployment is Lisa's step (needs her accounts); not claimed as verified.
