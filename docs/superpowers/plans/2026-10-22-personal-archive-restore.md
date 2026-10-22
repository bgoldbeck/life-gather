# Restore your personal archive into an account

Phase 3 of [FEATURE_PLAN.md](../../FEATURE_PLAN.md): "Add personal import/restore
... in separately scoped increments." This increment lets a person bring the
personal archive ZIP they downloaded (`lifegather-personal-archive/1`) back into
an account, for example after moving to a new installation or account.

## Scope

1. **Restore service** (`lifegather.memory.restore`): reads one archive ZIP,
   verifies the manifest, the records file hash/size and every original's
   path/size/SHA-256, and checks that each active photo/document record has
   exactly one matching original. Every record row must have exactly the
   exported fields with the column's type. Nothing is saved unless all checks pass.
2. **All-or-nothing write**: one database transaction inserts every collection in
   foreign-key order, with original IDs, sources, history, recorded times and
   valid-world dates kept unchanged and owned by the signed-in account. Originals
   go through the file-storage abstraction (local or S3); photo previews are
   regenerated from the originals. Stored files are removed if the write fails.
   The search index is rebuilt for restored sources and entities, and one audit
   entry records the restore. Portable SQLAlchemy Core only (no SQLite-only SQL
   in the restore itself), so it moves with the PostgreSQL work.
3. **Safe target**: restore only into an account with no saved records, and
   refuse when any restored ID already exists in the installation (for example the
   original account still holds them). Restoring the same archive twice is
   refused rather than duplicating records. IDs are not rewritten, so citations,
   corrections and history keep pointing at the same records.
4. **HTTP**: authenticated, CSRF-protected `POST /api/import/archive` taking the
   ZIP body (64 MiB limit, same as the download). No MCP/model tool: this is a file
   upload, and the model never receives the archive.
5. **Settings UI**: "Restore your records" card next to the download, with a file
   picker, confirmation, progress, restored counts and clear errors.
6. Starter asset types already saved in the archive are not listed twice in the
   new account.

## Not in scope

The JSON-only records download (no originals), merging an archive into an account
that already has records, ID remapping, partial/selective restore, older archive
formats, and settings/credentials/schedules (never exported).

## Acceptance checks

- Round trip: export an account with sources, corrections, purchases/money,
  maintenance, consolidations, asset types, chat, photos and documents; restore it
  into a new account on a fresh installation; a new export has identical
  collections and byte-identical originals, photo previews work and search finds
  restored records.
- Tampered records/originals, missing or extra originals, wrong formats, unsafe
  ZIP members and oversized uploads are refused with nothing saved.
- Non-empty target account and ID collisions are refused with nothing saved.
- Another account's data is untouched; the route rejects unauthenticated and
  non-CSRF requests; the Settings card shows success and error states.
