# Selective deletion and conversation retention

Two privacy controls added in v0.76.0. Both are permanent: deleted files and
conversations cannot be restored in the app, and undo does not apply to them.

## Delete several photos or documents

On **Photos** or **Documents**, open **Delete several photos/documents**, tick up
to 50 items, confirm that the originals cannot be recovered, then choose
**Delete N selected permanently**.

- The whole selection is deleted together or not at all. If any item changed since
  the page loaded, or is not yours, nothing is deleted and you are asked to reload.
- For each item the app does exactly what the single-item delete does: the record
  is marked deleted, any copy inside the database is cleared, a document's
  automatic extraction is erased, and one content-free audit receipt
  (`photo_deleted` / `document_deleted`) is written.
- The original file and photo preview are removed from file storage (the local
  files directory or S3 bucket) right after the change is saved. If storage is
  briefly unreachable, the next app start retries the removal.
- Reviewed text saved to memory, facts and their correction history remain, as do
  receipts or proposals that cite the item (they now show the original as deleted).
  To remove that saved text too, [delete the memory](MEMORIES.md#deleting-memories-v0840).
- Repeating a request for items already deleted succeeds without new receipts.

## Conversation retention

**Settings → Conversation retention** chooses how long chat conversations are
kept after their last activity: until you delete them (the default), 30 days,
90 days or 1 year. Before saving, the page shows how many conversations the new
setting would delete straight away.

- Last activity is the newest saved request in the conversation, or its creation
  time if it is empty. Conversations with a pending request wait until it finishes.
- Expired conversations are deleted when you save the setting, on app start and
  then hourly. Each deletion removes the conversation and its saved requests and
  replies and writes the same content-free `conversation_deleted` receipt as a
  reviewed delete ([conversation privacy](CONVERSATION_PRIVACY.md)).
- Memories, sources, photos, documents, purchases, assets, scans, credentials and
  settings are never touched by retention.
- Retention applies only to your account. Existing exports, backups and provider
  side history are unchanged; this is not forensic erasure of old backup media.

## Integration

All endpoints need the private session; writes also need same-origin/CSRF.

- `POST /api/photos/delete-many` with
  `{"photos": [{"photo_id", "expected_updated_at"}, ...]}` (1 to 50 unique items).
- `POST /api/documents/delete-many` with
  `{"documents": [{"document_id", "expected_updated_at"}, ...]}`.
- `GET /api/chat/retention[?preview_days=30|90|365]` returns the saved
  `conversation_days` and a `preview` with `eligible_count`.
- `PUT /api/chat/retention` with `{"conversation_days": 30|90|365|null}` saves the
  choice, applies it at once and returns `deleted_count`.

Migration `0031_conversation_retention` adds the nullable
`user_settings.conversation_retention_days` column with a check constraint. The
queries use portable SQL only. No model or MCP deletion tool is added.
