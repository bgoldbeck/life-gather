# Your records and original evidence files

In **Settings → Download your records**, select **Include original photos and documents
(ZIP)**, then **Download archive (ZIP)**. Leave it unchecked for the existing JSON
records download. No AI connection, vault key or external provider permission is
needed. Preparing a download changes no saved record and makes no provider request.

The ZIP contains your private saved content and is **not encrypted**. Keep it
private. You can [restore it into an account](#restoring-an-archive) with no saved
records, for example after moving to a new installation.
[Encrypted operator recovery](OPERATOR_RECOVERY.md) is the separate whole-installation
backup, including all users and installation secrets.

## Contents

- `records.json`: the `lifegather-records/6` copy of your source text,
  entities, original/corrected facts, history, distinct purchased units, exact
  monetary claims, maintenance tasks/revisions, saved asset types/fields/revisions,
  saved web research findings and save-request receipts,
  conversations and file metadata/text. Its own exclusions still
  describe this JSON file; original bytes live in the separate archive members.
- `originals/photos/…` and `originals/documents/…`: your active saved photo and document
  originals, byte for byte. Names use safe UUID identifiers and conservative file
  extensions; original filenames remain in the JSON records and manifest.
- `manifest.json`: `lifegather-personal-archive/1`, application version, snapshot
  time, records format, file IDs/paths, original filenames, MIME types, sizes and
  SHA-256 hashes. It maps each original to its record and verifies the records file.

Records and file metadata use one real PostgreSQL read transaction, so a concurrent
change cannot mix two versions in one archive. Original bytes come from
[file storage](FILE_STORAGE.md) and are checked against that snapshot's hashes;
a file deleted mid-download fails the archive instead of producing a partial one. The snapshot preserves original
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
retain their **10,000-row / 16 MiB JSON** limits. Preparation copies originals in chunks
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

## Restoring an archive

In **Settings → Restore your records**, choose a `lifegather-personal-archive/1`
ZIP, tick **Add this archive's records to my account** and select **Restore
archive**. The JSON-only records download cannot be restored, because it has no
original files.

Before anything is saved, the restore checks the ZIP (no extra, repeated,
encrypted or oversized members; stored or deflated only), the manifest, the
records file's size and SHA-256, and each original's path, size, MIME type and
SHA-256 against its photo/document record. Every active photo and document must
have exactly one original, and every record must have exactly the
`lifegather-records/6` fields with the right types. Archives written before
v0.83.0 (`lifegather-records/4`) still restore; they simply have no saved web
research findings. Format 5 archives restore without save receipts; original finding request IDs can be replayed through a conservative compatibility check. Unknown old duplicate request IDs cannot be recovered because format 5 never stored them. Photos are decoded again and
must match their recorded type and dimensions.

The restore is all or nothing. One database transaction inserts every record in
dependency order, owned by the signed-in account, with the **original IDs**,
sources, history, corrections, consolidations, exact money, recorded times and
valid-world dates unchanged, so citations and history still point at the same
records. Originals are saved through [file storage](FILE_STORAGE.md) (local or
S3); photo previews are regenerated from them. If any step fails, the transaction
rolls back and the stored files are removed. The search index is rebuilt for the
restored sources and entities, and one `personal_archive_restored` audit entry
records the archive's snapshot time.

Restore is refused (HTTP 409) when:

- the account already has saved records (so the same archive cannot be restored
  twice or mixed into existing data), or
- any record in the archive already exists in this installation, for example
  because the account it was downloaded from still holds it. IDs are never
  rewritten.

Starter asset types that the archive saved under the original account appear once
in the new account. Settings, credentials, connectors and scan schedules are not
in the archive and must be set up again. Deleted photos/documents return as
history without their files, as in the archive. Limits match the download: 64 MiB,
1,000 originals and 10,000 records.

The authenticated, CSRF-protected `POST /api/import/archive` takes the ZIP as the
request body with `Content-Type: application/zip` and returns the snapshot time,
per-collection counts, total records and number of originals. Errors: 413 over the
limits, 415 wrong content type, 422 invalid or modified archive, 409 as above, 429
while another restore runs. There is no MCP or model tool for restore; the model
never receives the archive. No schema change or migration.
