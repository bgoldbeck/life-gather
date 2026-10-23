# Two-account reliability check (Phase 3 gate)

Goal: prove the full create → evidence → recall → correction → restart →
backup/restore loop for two separate accounts in one installation, in the
browser against the real backend on PostgreSQL, and confirm nothing crosses
between the accounts. Fix any real bug the run finds.

## Scope

- `frontend/e2e/serve.py`: optionally provision a second synthetic account, and
  run uvicorn as a child process that a test can restart (a real process
  restart; the database and data directory are kept).
- `frontend/e2e/two-account-loop.spec.ts`, on a third throwaway installation:
  1. Two accounts sign in in separate browser contexts.
  2. Each adds its own assets; the same item name in the other account is not
     offered as a duplicate.
  3. Evidence: one account attaches a receipt photo, the other uploads a
     receipt document; neither appears in the other account.
  4. Recall: search finds only the signed-in account's records; the other
     account's asset and photo IDs answer 404.
  5. Correction: an ownership correction changes only that account's record
     and keeps the earlier statement in history.
  6. Restart: sessions, records and the correction survive a server restart.
  7. Backup/restore: each account's download holds only its own records;
     restoring one account's archive into the other is refused; restoring your
     own archive again changes nothing.
- Update `docs/END_TO_END_CHECKS.md` and the Phase 3 note in
  `docs/FEATURE_PLAN.md`.

No schema change. No AI provider, Google, SMTP or network service.
