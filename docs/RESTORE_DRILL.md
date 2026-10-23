# Backup expiry and restore drill (Phase 5.5 / 5.6)

Status: in progress on `claude/backup-expiry-restore-drill`.

## Scope

1. **Backup expiry after account deletion.** Deleting an account writes a
   minimal ledger entry (the deleted account id, when, and when the last
   installation backup holding it expires under `LIFEGATHER_BACKUP_RETENTION_DAYS`).
   No email, name or content is kept; entries are swept once backups expire.
2. **Deleted accounts stay deleted after a restore.** Restoring an older bundle
   can re-apply the live ledger so accounts deleted after the bundle was made
   are erased from the restored database before anyone can start it.
3. **Timed restore drill.** `python -m lifegather.recovery drill` verifies and
   restores a bundle into a throwaway directory and empty database, times it,
   and compares recovery point (bundle age) and recovery time with written
   RPO/RTO targets.

## Acceptance checks

- Deletion records a ledger row with the right expiry and no personal fields;
  the sweep removes only expired rows; the per-account role cannot read it.
- Restoring an old bundle with the ledger leaves no row of the deleted account.
- The drill reports RPO/RTO, passes within targets, fails (exit 1) when missed,
  and leaves no restored files behind.
