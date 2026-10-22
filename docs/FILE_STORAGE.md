# Private file storage

From v0.66.0 the bytes of original documents, original photos and photo previews
live in private object storage instead of inside the database. The database keeps
what LifeGather knows about each file (owner, name, size, SHA-256, extraction,
links and history) plus the file's storage key. Services, HTTP routes, MCP tools
and AI features never see where bytes physically reside.

All backends implement one interface in `lifegather.storage`:
`save(data, key)`, `get(key)`, `delete(key)` and `exists(key)`. Keys are generated
by the app (`users/<user>/documents/<id>/original`, `users/<user>/photos/<id>/original`
and `.../preview`), never taken from file names, and cannot escape their storage
root. Every read is checked against the recorded size and SHA-256 hash; a missing
or altered file is reported as unavailable rather than served as evidence.

## Local directory (default, self-hosting)

| Setting | Default | Notes |
| --- | --- | --- |
| `LIFEGATHER_STORAGE_BACKEND` | `local` | |
| `LIFEGATHER_STORAGE_DIR` | `<data dir>/files` | `/data/files` in Docker, so the existing `/data` mount keeps everything. |

Files are written atomically (temporary file, fsync, rename) with mode 0600 in
0700 directories. Nothing extra needs to run; no object-storage server is used.

## S3-compatible private bucket (hosted)

| Setting | Notes |
| --- | --- |
| `LIFEGATHER_STORAGE_BACKEND=s3` | |
| `LIFEGATHER_S3_BUCKET` | Required. Keep the bucket private (block public access). |
| `LIFEGATHER_S3_PREFIX` | Optional key prefix, e.g. one per installation. |
| `LIFEGATHER_S3_ENDPOINT_URL` | Optional, for MinIO/R2/B2 etc. HTTPS except on loopback. |
| `LIFEGATHER_S3_REGION` | Optional. |
| `LIFEGATHER_S3_ACCESS_KEY_ID` / `LIFEGATHER_S3_SECRET_ACCESS_KEY` | Optional; set both or neither. Without them boto3's standard credential chain (instance role, `AWS_*` variables) is used. |

The S3 backend needs the optional `s3` extra (`uv sync --extra s3`, which installs
boto3). The published image does not include it yet, so the S3 setting fails at
startup with a clear message until an image built with the extra is used. Storage
settings are environment-only and are not part of the installation JSON.

## Existing installations

Migration `0028_object_storage` adds the key columns and keeps the old byte
columns. Rows that still hold bytes in the database keep working. On startup the
app copies each one to storage, reads it back and checks its hash, and only then
clears the database copy, one row per commit. An interrupted or failed move is
retried on the next start and the database copy keeps being served meanwhile.
PostgreSQL reclaims the cleared space through its routine autovacuum.

Deleting a document or photo removes its stored files after the deletion commits.
If storage is unreachable at that moment the key is kept and the next startup
retries the removal.

## Backups and downloads

The personal archive ZIP reads originals through storage. Encrypted installation
recovery bundles stay self-contained and backend-independent: while a backup is
created, stored originals are copied back into the private database snapshot
(verified by hash) so the bundle format is unchanged. A restored installation uses
its own storage settings and moves those bytes out on its first start. A backup
fails if a stored original is missing or altered. Downgrading below `0028` is
refused while any file lives in storage; restore a bundle instead.
