# Per-account storage quotas

Status: delivered in 0.89.0. This completes Phase 5.3 of the
[feature plan](FEATURE_PLAN.md).

## What counts

An account's storage use is the bytes its live photos (original plus preview)
and documents keep in [file storage](FILE_STORAGE.md). It is computed from the
sizes already recorded on those rows, so there is no extra table to drift out of
step. Deleting a photo or document removes its stored files, so deleted ones do
not count. Database rows (memories, chat, history) are not counted.

## The limit

| Setting | Default | Notes |
| --- | --- | --- |
| `LIFEGATHER_STORAGE_QUOTA_MB` | `0` | Account-wide limit in MiB. `0` means no limit, which suits self-hosting. Every account gets the same limit. |

Like the other storage settings it is environment-only. When the limit is set,
these refuse a new file that would take the account past it, and store nothing:

- photo and document uploads (Photos, Documents, chat attachments);
- Gmail attachment intake, which records the attachment as not imported with
  the reason, as it does for other limits;
- restoring a personal archive, which refuses the whole restore (HTTP 409) when
  the files it would add do not fit.

Adding a file the account already has (same SHA-256) is not new storage and is
never refused. Lowering the limit below current use removes nothing; it only
stops new files until the account deletes some. The check runs inside the
serialized write that stores the file, so concurrent uploads cannot both pass.

The existing per-kind safety caps (200 photos / 256 MiB and 200 documents /
256 MiB per account) still apply whatever the account-wide limit is.

## Seeing usage

Settings has a **File storage** section showing space used, the limit (or "No
limit"), a bar when a limit is set, and photo and document counts and sizes.
The data comes from `GET /api/storage/usage` (signed-in account only):

```json
{"used_bytes": 3145728, "limit_bytes": null, "available_bytes": null,
 "photos": 2, "photo_bytes": 2097152, "documents": 1, "document_bytes": 1048576}
```

## Not included

Per-account limits that differ between accounts (for example paid plans, Phase
5.9) and an operator view of storage across accounts (Phase 5.8).
