# Full account deletion

Status: delivered in 0.87.0 (branch `claude/account-deletion`). Phase 5.5, the
"verified account deletion" part of the hosted account lifecycle; it also serves
self-hosted installations with several accounts.

## Goal

A signed-in person can permanently delete their own account from Settings. Every
row the account owns, every stored original file and every saved sign-in
(Gmail, AI providers, password, Google identity, sessions) is removed. Other
accounts are untouched. The personal archive stays the way to keep a copy first.

## Behavior

- `POST /api/account/delete` (signed-in, same-origin, CSRF token). The body must
  repeat the account's email address; accounts with a password must also give
  the current password (rate limited like sign-in). A wrong confirmation is
  refused with nothing changed.
- Stored originals (documents, photos and previews) are deleted first. If any
  delete fails the request is refused with no database change and can simply be
  retried; files already removed stay removed.
- Then, in one serialized transaction acting for the account (so row-level
  security is a second lock), every table with a `user_id` column is emptied of
  the account's rows in foreign-key order read from the database catalog, then
  the `users` row. New owned tables are covered automatically.
- Files added between the two steps are removed after the commit.
- The session cookie is cleared; the response reports rows and files removed.
- No migration and no deletion log: nothing about the account is kept.
  Installation backups (recovery bundles, provider snapshots) made before the
  deletion still contain the account until they expire; the docs say so.
- No MCP or assistant tool can delete an account.

## Acceptance checks

- Deleting one of two synthetic accounts leaves no row with its id in any table
  and no stored object under its prefix; the other account's row digest and
  files are unchanged.
- Wrong email, wrong or missing password, missing CSRF token or cross-origin
  requests change nothing.
- A storage failure refuses the deletion with every row intact; a retry
  completes it.
- The deleted account's session no longer authenticates.
- Settings shows the Delete account section and signs out after deletion.
- Full backend suite on PostgreSQL, mypy, ruff, frontend tests, lint and build.
