# Per-user storage quotas (Phase 5.3, last item)

Goal: each account's stored file usage is visible and can be capped, so a hosted
service can bound storage cost. Self-hosting stays unlimited by default.

## Scope
- Usage: the bytes an account keeps in file storage, counted from the live
  photo (original + preview) and document rows it owns. No new table; the rows
  already record exact sizes and deleted rows have their files removed.
- Limit: `LIFEGATHER_STORAGE_QUOTA_MB` (also settable in the installation
  configuration file). `0`, the default, means no account-wide limit.
- Enforcement: photo upload, document upload, chat attachments, Gmail attachment
  intake and personal-archive restore refuse a new file that would take the
  account past its limit. The check runs inside the existing serialized write,
  so concurrent uploads cannot both pass. Existing files are never removed.
- Settings: a Storage section shows used space, the limit (or "No limit") and
  photo/document counts. `GET /api/storage/usage`.
- Existing per-kind safety caps (200 photos / 256 MiB, 200 documents / 256 MiB)
  are unchanged.

## Acceptance checks
- Service tests: usage counts only the account's live files; uploads within the
  limit pass; an upload past the limit is refused with nothing stored; limit 0
  never refuses; restore past the limit is refused with no change.
- Route test for the usage endpoint, including another account's files not
  counted.
- Frontend test for the Settings storage section (with and without a limit).
- Full backend suite on PostgreSQL, mypy/ruff, frontend tests/lint/build.
