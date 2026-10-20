# Your records and original evidence files

In **Settings → Download your records**, select **Include original photos and PDFs
(ZIP)**, then **Download archive (ZIP)**. Leave it unchecked for the existing JSON
records download. No AI connection, vault key or external provider permission is
needed. Preparing a download changes no saved record and makes no provider request.

The ZIP contains your private saved content and is **not encrypted**. Keep it
private. It is a portable copy for inspection, with no app import/restore action.
[Encrypted operator recovery](OPERATOR_RECOVERY.md) is the separate whole-installation
backup, including all users and installation secrets.

## Contents

- `records.json`: the `lifegather-records/3` copy of your source text,
  entities, original/corrected facts, history, distinct purchased units, exact
  monetary claims, maintenance tasks/revisions, conversations and file metadata/text. Its own exclusions still
  describe this JSON file; original bytes live in the separate archive members.
- `originals/photos/…` and `originals/documents/…`: your active saved photo and PDF
  originals, byte for byte. Names use safe UUID identifiers and conservative file
  extensions; original filenames remain in the JSON records and manifest.
- `manifest.json`: `lifegather-personal-archive/1`, application version, snapshot
  time, records format, file IDs/paths, original filenames, MIME types, sizes and
  SHA-256 hashes. It maps each original to its record and verifies the records file.

Records and original bytes use one real SQLite read transaction, so a concurrent
change cannot mix two versions in one archive. The snapshot preserves original
IDs, sources, confidence/unknowns, correction/consolidation history, custom details,
valid-world dates and recorded times. A common filename or value does not combine
distinct records or purchased units.

Only your account's records/files are included. Credential records, authentication,
sessions, settings, connector configuration, jobs/schedules, processing caches,
search indexes and installation configuration are excluded. Original files and
saved text can themselves contain sensitive information; this download does not
redact your content. Previews and originals already deleted at the snapshot are
excluded; historical file metadata can remain. Later changes do not alter a copy
already prepared.

## Limits and failure behavior

The first archive slice supports at most **1,000 originals** and **64 MiB total ZIP
bytes**, including records, manifest, headers and central directory. Records also
retain their **10,000-row / 16 MiB JSON** limits. Preparation streams BLOBs in chunks
into a bounded in-memory archive; it never copies a whole database or writes a
temporary all-user backup file.

Stored original lengths/hashes are checked before a complete response is returned.
Missing active originals, corrupt data or an exceeded limit produce no partial
download. For large archives, use the JSON download and individual original-file
downloads, or ask the installation owner for help. The app does not automatically
substitute an all-user operator backup. Refresh an expired session and try again.

The authenticated, CSRF-protected `POST /api/export/archive` accepts an empty JSON
object and returns an attachment with `application/zip`, `no-store` and `nosniff`.
It rejects arbitrary body fields/owner overrides. Existing `POST /api/export/records`
and records-format compatibility are unchanged. No new MCP/model tool, dependency,
schema or migration is added by the archive operation. Maintenance records use
the application's later migration 0024; archives preserve their full sourced history.
