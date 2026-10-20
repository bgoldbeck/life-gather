# Review and delete a private conversation

Open **Your conversations** in the assistant, then use the trash/review action
beside the conversation you want to remove. Review its current title and exact
number of saved requests and replies. **Cancel deletion** returns without removing
anything. Your unsent draft remains available.

When pending chat requests exist, use **Stop pending chat requests** first. This
also handles requests displayed as interrupted after a restart. Review the updated
preview, select **Permanently delete this conversation**, then **Delete permanently**.
This operation has no undo in the app. A changed conversation requires a new
preview; deletion is never retried automatically with a new version.

## Removed and retained data

Deletion removes that account's conversation record and its saved chat requests
and assistant replies from the live workspace. It removes neither another account's
conversation nor a different conversation you have open. When deleting the current
one, its saved messages, evidence view and retry state clear; the unsent draft and
other conversations remain. A delayed page or reply cannot restore the removed entry.

**Independently saved records remain:** original memory notes, source episodes,
profile statements and correction history, purchases, photo/PDF originals and
extracted evidence, graph facts, scan jobs/schedules, credentials, settings and
usage budgets. A request explicitly saved as evidence can therefore still exist
in Memories or a profile after its conversation is removed. Deleting the transcript
does not reverse actions performed through it or reset AI usage.

Stopping pending chat requests is separate from canceling already-created scan
jobs; use **Scans** for those. A provider request already transmitted cannot be
recalled. Existing exports, backups, provider-side history and other saved copies
remain unchanged. This control removes live transcript rows and makes no promise
of forensic erasure from SQLite storage, old backup media or another service.

The app retains a minimal owner-scoped deletion receipt in its existing audit log:
conversation identifier, deletion time and server-owned workflow attribution.
It contains no title, prompt, reply or transcript snippets. This permits a confirmed
delete retry to report success after a lost response, without recreating messages.
Personal JSON/ZIP downloads exclude removed conversation/turn rows; independently
saved source copies and this content-free audit remain in their stated scope.

## Integration contract

All three endpoints require the private session, same-origin/CSRF protection and
strict JSON bodies. Conversation identifiers stay in the URL; owner overrides
are rejected. No model or general MCP deletion tool is added.

- `POST /api/chat/conversations/{id}/deletion-preview` with `{}` returns
  `lifegather-conversation-deletion/1`, authoritative title, exact request/state
  counts, pending count and a version token. It reads aggregate metadata in one
  real SQLite snapshot, without loading full prompts or replies.
- `POST /api/chat/conversations/{id}/stop-pending` accepts `preview_token`, checks
  it under the serialized writer guard and marks pending requests canceled. It
  returns an updated preview; it does not delete the conversation.
- `POST /api/chat/conversations/{id}/delete` accepts `preview_token` and strict
  `confirmed: true`. It rechecks the version, refuses pending requests, then deletes
  only the owned requests and conversation and writes one audit receipt atomically.
  A matching owner receipt permits idempotent replay after deletion.

Append, completion or cancellation changes invalidate the preview. Stale mutations
return 409; missing/foreign conversations, pending-delete attempts, invalid bodies
and expired/missing sessions are refused without partial deletion. API responses
use `no-store`. Chat completion uses the same immediate writer transaction, so
cancellation cannot be overwritten from a stale read and missing turns cannot be
recreated by late completions. No schema, migration or dependency is added;
migration remains 0023.
