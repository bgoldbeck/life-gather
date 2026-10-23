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

`frontend/e2e/two-account-loop.spec.ts` runs the Phase 3 loop for **two accounts
in one installation**, each in its own browser context, and checks at every step
that nothing crosses between them:

1. **Sign in**: both accounts are signed in at the same time.
2. **Add**: each adds its own assets. Both add an item with the same name; neither
   is offered the other account's item as a possible duplicate, and each list
   holds exactly one.
3. **Evidence**: the first attaches a receipt photo to an asset, the second
   uploads and reviews a receipt document. Neither appears in the other
   account's Photos or Documents view.
4. **Recall**: search everything finds the signed-in account's asset, photo and
   document and nothing from the other account. Requesting the other account's
   asset, purchases, photo (details, links, preview, original) or document
   (details, original) answers exactly like an ID that never existed.
5. **Correct**: an ownership correction ("I sold this item", with a note) makes
   the asset a historical record; the earlier stated ownership stays in history
   beside it. The other account's same-name item is unchanged.
6. **Restart**: the server process is stopped and a new one started on the same
   database and data directory. Both sessions survive, and the asset, its photo,
   the correction and the separation of search results are all intact.
7. **Back up**: each account's JSON download contains its own records and none
   of the other account's names, files or email address.
8. **Restore**: restoring the first account's archive into the second account is
   refused ("belong to another account") and adds nothing; restoring it into
   the first account again changes nothing.
9. **Sign out** of one account leaves the other signed in.

All data is synthetic: the accounts (`e2e.tester@example.test` and
`e2e.second@example.test`), records and the fixtures in `frontend/e2e/fixtures/`. No AI provider, Google, SMTP or network
service is used.

## How they run

`frontend/e2e/serve.py` starts one throwaway installation: a new PostgreSQL
database, a temporary data directory, one local account created the way
`python -m lifegather.setup_account` does, and uvicorn serving the built UI from
`frontend/dist`. Playwright starts three of these (ports 8797 and 8798 for the
core journeys, 8799 with a second account for the two-account loop) and removes
every database and data directory when it finishes. uvicorn runs as a child of
`serve.py`; the restart step creates `lifegather-e2e-<port>.restart` in the
system temporary directory, and `serve.py` stops the server, starts a new one and
removes the file.

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

- 2026-10-23, two-account loop: no bugs found. Isolation held at every step,
  including direct requests for the other account's record IDs, search, the
  duplicate check, downloads and restore. Two behaviours are by design: a sold
  item leaves the default Assets list (tick *Include historical records*), and
  the original stated ownership stays a current statement beside the correction
  rather than being superseded, since a correction never overwrites an
  independent source.

  The run did find a bug in the check runner itself: Playwright stopped each
  throwaway server with SIGKILL, so `serve.py` never dropped its database or
  removed its temporary data directory, and every run left them behind. The
  servers are now stopped with SIGTERM and clean up after themselves.
- 0.80.0: the first run found that restoring a personal archive failed with
  "Archive record is missing a required value" whenever it contained a non-PDF
  document (text, Markdown, CSV, Word or Excel). The export leaves the unused
  page count empty for those formats and restore rejected the empty value before
  filling it in. Fixed, with a backend regression test.

## Limits

- Chromium only, desktop viewport.
- Not covered yet: Google sign-in, chat with a configured AI provider, Gmail
  scans, and a full container restart (the restart step restarts the server
  process, not Docker). Route-by-route account isolation has its own backend
  tests.
- GitHub Actions is disabled for this repository, so the checks run locally or in
  an agent session, not on every push.
