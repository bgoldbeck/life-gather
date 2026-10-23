# Backup expiry and restore drill (Phase 5.5 / 5.6)

Status: delivered in 0.100.0. A live drill against the hosted database is an
operator step (see the end of this page).

## Backup expiry after account deletion

[Account deletion](ACCOUNT_DELETION.md) removes the account's rows and stored
files at once. Installation backups made before that moment still hold the
account until the operator's retention removes them. `LIFEGATHER_BACKUP_RETENTION_DAYS`
(default 35, 1 to 3650) states that retention period.

When an account is deleted, LifeGather writes one entry to the
`deleted_accounts` table (migration `0040_deleted_accounts`):

| Column | Meaning |
| --- | --- |
| `account_id` | The deleted account's random id. No email, name or content. |
| `deleted_at` | When it was deleted (Unix seconds). |
| `backups_expire_at` | `deleted_at` plus the retention period: the last backup holding the account is gone by then. |

`POST /api/account/delete` also returns `backups_expire_at`. The table is a
system table: the per-account database role cannot read it, and no HTTP, MCP or
assistant route shows it. An hourly sweep removes entries once
`backups_expire_at` has passed, so after the retention period nothing about the
account is left anywhere.

The entry is written just after the deletion commits. If that write fails, the
deletion still stands and an error is logged (it shows on the
[Operations page](OPERATIONS.md)).

**Keep the promise in the backups themselves.** LifeGather does not manage
backup files. Set the retention of every copy to at most
`LIFEGATHER_BACKUP_RETENTION_DAYS`:

- recovery bundles (`python -m lifegather.recovery backup`): delete files older
  than the period, for example with a lifecycle rule on the R2 or S3 bucket that
  stores them, or a cron job on TrueNAS;
- managed PostgreSQL point-in-time recovery: a window no longer than the period;
- bucket versioning or snapshots of stored files: expire old versions within
  the period.

## Deleted accounts stay deleted after a restore

Restoring an older bundle would bring back accounts deleted after it was made.
Export the live ledger first and give it to the restore:

```sh
python -m lifegather.recovery export-deletions /private/deleted-accounts.json
LIFEGATHER_DATABASE_URL=postgresql://lifegather:PASSWORD@db:5432/lifegather_restored \
  python -m lifegather.recovery restore /backups/installation.lgbackup /private/recovered \
  --deleted-accounts /private/deleted-accounts.json
```

The file lists only ids and times (mode 0600, never overwritten). After the
snapshot loads, the restore deletes those accounts' rows (their files are inline
in the bundle, so they go too), copies the entries into the restored ledger,
and then runs the usual validation. The summary reports `erased_accounts`.
If the live database is lost, the newest bundle's own ledger covers every
deletion before it was made.

## Timed restore drill

```sh
LIFEGATHER_DATABASE_URL=postgresql://lifegather:PASSWORD@db:5432/lifegather_drill \
  python -m lifegather.recovery drill /backups/installation.lgbackup \
  --staging-dir /private-staging --deleted-accounts /private/deleted-accounts.json \
  --report /private/drill-2026-10-23.json
```

The drill does a full restore (authenticate, check hashes, load the snapshot
into the new, empty database, erase deleted accounts, validate) into a throwaway
directory, then removes that directory. It prints one JSON report and, with
`--report`, writes it to a new file:

- `recovery_point_seconds`: how old the bundle was when the drill began. This is
  the data you would lose if you restored it now.
- `recovery_time_seconds`: how long the full restore took.
- `rpo_target_seconds`, `rto_target_seconds` and `passed`.
- `past_retention`: the bundle is older than `LIFEGATHER_BACKUP_RETENTION_DAYS`
  and should already have been deleted.
- `bundle`: version, migration, row counts and `erased_accounts`.

It exits 0 when both targets are met and 1 when one is missed or the restore
fails. It never starts the app. The database is left loaded so you can inspect
it; drop it afterwards and use a new empty one for each drill.

### Written targets

| Setting | Recovery point (RPO) | Recovery time (RTO) |
| --- | --- | --- |
| Self-hosted, daily bundle | 24 hours (`--rpo-hours 24`, default) | 60 minutes (`--rto-minutes 60`, default) |
| Hosted, managed PostgreSQL with point-in-time recovery | 15 minutes for the database; 24 hours for the bundle copy | 60 minutes |

Run a drill at least once a month and after each release that adds a
migration. Keep the reports; they are the record that a restore works.

### Tests

`backend/tests/test_restore_drill.py` creates a synthetic installation with two
accounts, makes a bundle, deletes one account, and checks that: the ledger keeps
only the id and times, the account role cannot read it, the sweep forgets only
expired entries; a plain restore brings the account back while a restore with
`--deleted-accounts` does not; the drill passes within its targets, writes the
same report it prints, leaves nothing in staging and fails (exit 1) when a target
is missed; and a bundle older than the retention period is flagged.
`test_account_deletion.py` checks the API's `backups_expire_at` and the ledger
entry.

## Lisa's step: the live hosted drill

This cannot run from a cloud session; it needs the hosted database. Once the
hosted site has a managed PostgreSQL database:

1. Set `LIFEGATHER_BACKUP_RETENTION_DAYS` on the hosted app to the period you
   publish in the privacy policy (35 days unless you choose otherwise), and set
   the same lifecycle on the backup bucket and the database's recovery window.
2. Make a bundle from the hosted app and export the ledger
   (`backup`, then `export-deletions`).
3. Create a new, empty database (C collation) on the managed server, then run
   the `drill` command above against it from the app image.
4. Check `passed` is `true`, keep the report, and drop the drill database.
