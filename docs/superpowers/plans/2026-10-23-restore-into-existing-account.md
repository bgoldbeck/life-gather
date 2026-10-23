# Restore an archive into an account that already has records

Status: in progress (branch `claude/restore-into-existing-account`).

## Goal

Today a personal archive restores only into an empty account. Let a user restore
an archive into their account even when it already holds records, for example to
bring back records lost or removed after the backup was made, or to add a
backup's records to an account that has started fresh records.

## Behavior

- Records whose ID is already in this account are left exactly as they are. The
  current record wins, even if it changed since the archive was made, so newer
  corrections, deletions of memory text and later history are never overwritten.
- Records the account does not have are added with their original IDs, dates,
  provenance and history, together with their originals, in one transaction.
- Restoring the same archive twice adds nothing the second time.
- The restore is refused with nothing changed (HTTP 409) when an archive record's
  ID belongs to another account in this installation, or when a new archive record
  clashes with a different record already in the account on a natural key (the same
  email source, request, starter asset type or current history head). IDs are never
  rewritten and distinct records are never merged.
- The response reports how many records were added and how many were already
  present; the audit entry records the snapshot time and the added count.

## Acceptance checks

- Empty-account restore behaves exactly as before.
- Restoring into an account that holds the same records adds only the missing
  ones and their originals; current rows are unchanged.
- A second identical restore adds nothing.
- A clash on a natural key or another account's IDs returns 409 and writes
  nothing (no rows, no stored files).
- Settings shows the added/already-present counts.
- Full backend suite on PostgreSQL, mypy, ruff, frontend tests, lint and build.
