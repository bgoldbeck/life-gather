# Reviewed private conversation deletion

Baseline checked October 19, 2026: clean main9fbb039d4f9733d4f30f402695928c13d972f13e, v0.53.0, migration0023, one checkout, fresh branches/open PRs with no overlap. Its source passed 583 backend/253 frontend tests and quality/build/browser/recovery checks. The guarded image publisher is running; this early scope commit leaves the active checkout unchanged. Implementation follows release/actual-image verification and another baseline check. Target v0.54.0 if main has not advanced. No agents.

Chat stores private prompts and replies but has no conversation deletion flow. Add a deliberately bounded privacy control for one owned conversation. A preview must clearly state that it removes saved chat requests/replies while retaining independently saved memories, profile corrections, files, purchases, scans, settings, usage, prior exports/backups and provider-side history. This is not general evidence erasure, account deletion, undo or a promise of forensic storage sanitization.

Implement a framework-independent chat/privacy.py service using existing owner checks and serialized SQLite writes. Preview exact request/state counts and a deterministic revision token inside one real read snapshot, using bounded aggregate metadata instead of full replies. Recompute under BEGIN IMMEDIATE before any mutation. Changed counts/state/identity require review again. Strict bodies refuse owner overrides and missing/false confirmation. No schema or dependency change.

Provide a separate explicit Stop pending chat requests operation guarded by that preview token, including old pending rows displayed as interrupted. Mark them canceled using the existing stopped-request result; re-preview before deletion. Do not silently stop requests during deletion or claim to stop already-created scan jobs. Keep usage budgets. Test cancellation/finish races and use the existing serialized writer guard for terminal transitions if needed. Saved domain actions remain independent.

Delete only the owned Turn rows and Conversation, atomically, after fresh review and explicit confirmation, refusing pending turns. Store one minimal existing Audit conversation_deleted entry with owner/id/time/server-owned origin and no title/prompt/reply snippets. Its owner-scoped tombstone permits idempotent deletion retries without accepting another user's guessed IDs. Late completion and old requests cannot recreate the deleted transcript. No model or MCP general deletion tool. Thin authenticated CSRF-protected POST preview/stop/delete adapters.

UI: explicit review action beside each Your conversations entry and a focused ConversationDelete component. Show title, exact count, retained scope, pending stop/re-review, Cancel and an explicit permanent-delete confirmation. Prevent duplicate mutations and stale/late/unmounted responses. Remove only the deleted entry; deleting the active conversation clears saved turns/evidence/selection/retry state, preserves unsent draft and other conversations, and invalidates late loads/pagination so removed entries cannot reappear. Review of another conversation must preserve current conversation state. Accessible keyboard/focus behavior and responsive semantic colors; no destructive action hidden in normal navigation.

Acceptance: two owners/multiple conversations, stale previews after append/completion/cancellation, invalid confirmation/owner overrides, pending/interrupted stop flow, late finish and concurrent deletion/replay, rollback and one content-free tombstone. Retain independently saved memory/custom history, files/scans/credentials/settings/usage. Deleted-ID append/recall/organize refuse; JSON/ZIP omit transcript rows while retained source copies remain explicit. HTTP session/CSRF/isolation. UI preview/cancel/stop, failures/conflicts/duplicate clicks/late-unmount, selected vs other deletion, paging and draft preservation. Browser verifies review/cancel and retained data at desktop/390px; final deletion is tested programmatically on isolated synthetic fixtures. Full checks/builds, graph+HTML, final clash checks and standing source/image release. No live personal data deletion, provider calls, existing-installation deployment or security-setting change.

## Implementation and acceptance evidence

The service and three HTTP adapters implement aggregate-only snapshot previews,
serialized fresh-version mutations, a separate pending stop, explicit confirmation
and atomic owner-scoped deletion receipts. Completion now shares the immediate
writer guard: a deterministic race test reproduced the old stale completion
overwriting cancellation and passes with the guarded terminal transition.

Nine backend privacy cases cover isolation, state changes, deletion replay and
rollback, metadata-only bulk previews, strict HTTP/session/CSRF boundaries and
retention of exact record collections, photo/PDF bytes, vault secrets, queued scans
and usage. The pre-existing scan transport test now holds its worker paused while
checking a queued fixture; actual worker progress/cancellation tests remain real.
This removes a reproduced fixture race where the worker finished before the test's
cancel assertion. The final full backend run passes all 592 cases (436.27s).

All 266 frontend tests across 48 files pass, including 13 new privacy interactions.
Ruff lint/format and strict mypy pass for 229 source/test/smoke files; TypeScript,
frontend lint/format and production build pass. The wheel contains the new privacy
service. Code-only, single-worker Graphify extraction and HTML export completed:
3,298 nodes and 14,252 edges, with no model calls or configuration changes.

Actual isolated browser review/cancel preserves the unsent draft, transcript and
custom profile correction, and returns focus to the review action. Desktop light
and 390px dark layouts pass with no page overflow; review uses the full assistant
width. No real records were deleted. A mounted-source Linux smoke preserves the
deletion receipt, absent transcript, source corrections, originals, both owners
and private credentials through encrypted recovery of a 42.9 MB synthetic database.
Clean-main image publication and fresh-image recovery verification follow source
acceptance; no existing installation is redeployed.
