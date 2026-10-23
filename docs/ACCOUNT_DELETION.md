# Account deletion (Phase 5.5)

Status: delivered in 0.87.0. This is the "verified account deletion" part of the
hosted account lifecycle; it also serves self-hosted installations with several
accounts. Turnstile bot checks and terms acceptance remain for 5.5.

## What the user does

Settings → **Delete account**. The person types their account email, ticks the
acknowledgement and, if the account has a password, gives the current password.
The page suggests downloading the personal archive first; there is no undo.
After deletion the browser returns to the sign-in page.

## What is removed

`POST /api/account/delete` with `{"email": ..., "password": ...}` (signed in,
same origin, CSRF token):

1. Stored originals (document files, photo originals and previews) are deleted
   from file storage (local directory or S3-compatible bucket). If any delete
   fails, the request is refused (503) with no database change; files already
   removed stay removed and a retry finishes the job.
2. One serialized transaction, acting for the account so row-level security is a
   second lock, deletes the account's rows from every table with a `user_id`
   column, in foreign-key order read from the database catalog, and then its
   `users` row. That covers records, history, audit entries, conversations,
   scans and schedules, saved Gmail and AI credentials, the password, Google
   identity links and every session. Tables added later are covered
   automatically; a table that references account rows without its own
   `user_id` makes deletion fail loudly rather than leave rows behind.
3. Files added between steps 1 and 2 are removed after the commit.

The response reports `rows` and `files` removed and clears the session cookie.
Signing in again with the same Google account starts a new, empty account.

Only the account's random id and two times are kept, in the `deleted_accounts`
ledger, until every installation backup made before the deletion has expired;
then that entry is removed too (0.98.0, see [backup expiry](RESTORE_DRILL.md)).
Gmail and AI provider grants are deleted locally but not revoked at Google or the
provider; the person can revoke them in their Google account or provider console.

## Limits and confirmations

- A wrong email or password is refused (400) with nothing changed. Password
  checks share the sign-in rate limits (per client and per account).
- No MCP tool or assistant action can delete an account.
- Installation backups (recovery bundles, PostgreSQL or bucket snapshots) made
  before the deletion still contain the account until the operator's retention
  removes them. `LIFEGATHER_BACKUP_RETENTION_DAYS` states that period, the
  response's `backups_expire_at` says when the last copy is gone, and restores
  can erase deleted accounts again. See [backup expiry](RESTORE_DRILL.md).

## Tests

`backend/tests/test_account_deletion.py`: two synthetic accounts with records,
documents, photos, chat, scans and research; after deleting one, no table holds
its id, no stored file remains under its prefix, its session no longer
authenticates, and the other account's row digest and files are unchanged.
Wrong confirmations, missing CSRF tokens, cross-origin requests and storage
failures change nothing; a retry after a storage failure completes.
`frontend/src/AccountDeletion.test.tsx` covers the Settings form.
