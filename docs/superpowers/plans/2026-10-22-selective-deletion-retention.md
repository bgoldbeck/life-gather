# Selective deletion and retention (Phase 3 increment)

Goal: let a user remove several originals at once and stop keeping old chat
transcripts forever, without weakening provenance for records they keep.

## Scope

1. **Delete several photos or documents together.** Photos and Documents pages
   gain a select mode. One confirmed request deletes up to 50 owned items in one
   transaction with per-item version checks (all or nothing). Each item uses the
   existing deletion: the row is marked deleted, inline copies cleared, one audit
   receipt per item, and stored files removed from object storage right after the
   commit (the existing startup sweep retries failures).
2. **Chat conversation retention.** Settings offers "Keep conversations: forever /
   30 / 90 / 365 days after their last activity". Stored per account in
   `user_settings` (migration). Expired conversations without pending requests are
   deleted with the existing `conversation_deleted` receipt; saved evidence stays.
   The sweep runs on startup, hourly, and right after the setting is saved. The
   settings page previews how many conversations a choice would remove now.

Deletion is permanent and not undoable (stored bytes are gone). Retention never
touches memories, sources, purchases, assets or originals.

## Acceptance checks

- Bulk delete: owner isolation, stale version refuses the whole batch, retry of an
  already deleted item is idempotent, stored files removed, duplicates rejected.
- Retention: only expired, owned, non-pending conversations go; turns removed;
  audit receipt written; off by default; preview count matches the sweep.
- Portable SQL (no SQLite-only constructs) so it carries to PostgreSQL.
- UI tests for select/delete and the retention setting.
