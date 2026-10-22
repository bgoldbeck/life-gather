# File storage abstraction

Date: 2026-10-22. Requested by the user: keep original documents and photos in
private object storage behind one interface, with a local directory for
self-hosting now and S3-compatible private buckets later, chosen by configuration.

## Scope

- `lifegather.storage`: one `ObjectStorage` interface (`save`, `get`, `delete`,
  `exists` by object key) with two backends:
  - `LocalStorage`: files under `LIFEGATHER_STORAGE_DIR` (default
    `<data_dir>/files`, so `/data/files` in Docker), written atomically with
    private permissions; keys can never escape the directory.
  - `S3Storage`: a private S3-compatible bucket and optional prefix. Uses the
    optional `s3` extra (`boto3`), so the default image gains no dependency.
- Settings `LIFEGATHER_STORAGE_BACKEND=local|s3` plus bucket/prefix/endpoint/
  region/credentials for S3. Secrets come from the environment, never source.
- Migration `0028_object_storage` adds `documents.original_key`,
  `photos.original_key` and `photos.preview_key`. No column is dropped.
- Document and photo upload, download, preview, extraction and deletion use
  storage; the knowledge graph only stores the key and the content hash. Reads
  verify size and SHA-256 before returning bytes.
- Existing files keep working: rows that still hold bytes in the database are
  read from there, and on startup the app copies each one to storage, verifies
  it, then clears the database copy. Interrupted runs resume safely.
- Personal archive ZIP reads originals through storage.
- Encrypted installation recovery stays self-contained: the bundle's database
  snapshot has every stored object copied back inline (format unchanged), so a
  bundle restores into either backend; the restored app moves them out again.

## Acceptance checks

1. Local and S3 backends pass one shared contract test (S3 with a fake client);
   unsafe keys are refused.
2. Uploading, downloading, previewing and deleting documents and photos works
   with bytes only in storage; deletion removes the stored objects.
3. A database with pre-existing inline originals still serves them and, after
   startup migration, has them in storage with the database copy cleared.
4. Personal archive and recovery backup/verify/restore include stored originals.
5. `uv run pytest`, `ruff check`, `ruff format --check`, `mypy` pass from
   `backend/`.

## Out of scope

Database engine changes (separate PostgreSQL work), new upload types, orphan
sweeping beyond retrying failed deletes, Docker image publication from the cloud.
