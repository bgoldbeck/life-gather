# End-to-end reliability checks

Browser-driven checks walk through core tasks the way a person would, against the
real backend on PostgreSQL. They complement the backend and component tests,
which use the same database but no browser. Phase 3 of the
[feature plan](FEATURE_PLAN.md#phase-3-prove-tracking-is-dependable).

## What they cover

`frontend/e2e/core-journeys.spec.ts` runs these journeys in order, in one
signed-in Chromium session that builds on one workspace:

1. **Sign in**: a wrong password is refused; email/password sign-in works and the
   session survives a reload.
2. **Add an asset** with the manual form. Entering the same name again shows
   "Possible duplicate assets" and offers linking instead of silently creating or
   merging; cancelling leaves exactly one record.
3. **Attach a receipt photo** from the asset's own Photos & Documents section. The
   Photos view shows it attached to that asset and its original downloads byte for
   byte.
4. **Upload a receipt document** (text), review the extracted text and save it to
   memory.
5. **Search everything** finds the asset and the document and opens each exact
   record; an unmatched query returns nothing.
6. **Back up** with *Download archive (ZIP)* including originals.
7. **Restore** that archive into a second, separate installation (its own
   database and data directory) in a fresh browser context: the asset keeps its
   evidence and photo, the photo original is identical, the document is
   searchable, and restoring the same archive again is refused.
8. **Sign out** ends the session; the API then answers 401.

All data is synthetic: the account (`e2e.tester@example.test`), records and the
fixtures in `frontend/e2e/fixtures/`. No AI provider, Google, SMTP or network
service is used.

## How they run

`frontend/e2e/serve.py` starts one throwaway installation: a new PostgreSQL
database, a temporary data directory, one local account created the way
`python -m lifegather.setup_account` does, and uvicorn serving the built UI from
`frontend/dist`. Playwright starts two of these (ports 8797 and 8798) and removes
both databases and data directories when it finishes.

From `frontend/`, with PostgreSQL (with pgvector) reachable:

```sh
npm ci
(cd ../backend && uv sync --locked)
LIFEGATHER_E2E_DATABASE_URL=postgresql://postgres:secret@127.0.0.1:5432/postgres \
  npm run test:e2e
```

`LIFEGATHER_E2E_DATABASE_URL` names a server whose user may create databases; it
falls back to `LIFEGATHER_TEST_DATABASE_URL`. `npm run test:e2e` builds the UI
and then runs `playwright test`. The first time on a new machine, install the
browser with `npx playwright install chromium` (about 170 MB). Failure traces and
screenshots go to `frontend/test-results/` (ignored by Git); open a trace with
`npx playwright show-trace <path>/trace.zip`.

`npm test` (Vitest) does not run these checks.

## Findings

- 0.79.0: the first run found that restoring a personal archive failed with
  "Archive record is missing a required value" whenever it contained a non-PDF
  document (text, Markdown, CSV, Word or Excel). The export leaves the unused
  page count empty for those formats and restore rejected the empty value before
  filling it in. Fixed, with a backend regression test.

## Limits

- Chromium only, desktop viewport.
- Not covered yet: Google sign-in, chat with a configured AI provider, Gmail
  scans, a container restart, and two accounts in one installation (account
  isolation has its own backend tests).
- GitHub Actions is disabled for this repository, so the checks run locally or in
  an agent session, not on every push.
