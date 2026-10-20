# Sourced one-off maintenance tasks

Target v0.55.0. Fresh baseline checked October 19, 2026: clean main 2767c774aadef5140f1b10f6ca6bae81ceaa8870, v0.54.0, migration 0023, one checkout, no other feature branches or open PRs/issues. PR79 is merged; its full592 backend/266 frontend checks, actual-image recovery and immutable/latest publication passed. Both remote tags resolve to sha256:79d8ed45868b2c4a8526311559c02ee3d91d7f50a2f9ded079f47cf0f78222ea with expected labels. Current source and scoped Graphify/rg review confirm maintenance remains only a freeform profile field. No agents. Current profile maintenance is only freeform text; add a useful dated workflow without inferring schedules or claiming fitment/coverage.

Architecture: a framework-independent maintenance service and two typed owner-constrained tables, with Alembic0024 from0023. A stable task references its original owned asset/place and creation source/request. Immutable revisions carry title, optional calendar due date, explicit IANA timezone, state(open/completed/canceled), optional stated completion date, source, previous revision, request fingerprint, recorded time and superseded time. Enforce one current revision with a partial unique index, source/parent/previous owner FKs, strict state/date constraints and serialized writes. Original linked record ID stays fixed; reads project the current consolidated identity. No name-based task deduplication or retargeting.

Every create/change requires an original user statement. Store it unchanged inside a clearly labelled manual source containing the explicitly supplied structured form fields; those fields remain user statements, never independently verified recommendations. Do not infer original event dates, ownership, intervals, completion dates, money, fitment or warranty. Keep completion/due world dates distinct from system recording time. Create/change save source, revision and minimal audit atomically. A fresh state token includes current revision and original/current target identity. Changed state/context refuses409 and requires explicit reload; exact concurrent/lost-response retries use stable request receipts before version checking and never rewind a later revision. Changed payload using the same request ID refuses. Cancel/reopen are revisions, not deletion.

Use thin HTTP private session/CSRF adapters and MCP list/get/history/create/revise tools. Closed bounded DTOs reject owner overrides; server derives origins. Keep the built-in model write allowlist unchanged, with no automatic model/provider/connector call. List/read/history use bounded queries and owner/filter-bound cursors. Open tasks sort known due dates first then date/id, unknown dates last; stable opaque cursors validate owned current revisions and selected scope, stale cursor requires refresh. Per-task Today/Past due/Upcoming/Unscheduled uses its stated timezone and the server clock, with no inferred date. Completed/canceled remain browseable. Completion date may be explicitly unknown; non-completed states cannot carry a completion date. No recurrence, mileage triggers, notifications, timers, scheduler or external-action consequence.

UI: scoped maintenance section in the selected Profiles record, listing tasks, source/history, explicit unknown due date, timezone and original statement, with create and correction/state change forms. Read a fresh version before editing, preserve drafts on failure and make409reload explicit; keep stable request ID for exact retries, reject duplicate clicks and late target/unmount responses. Changing profile keys cancels reads/forms. Add a global Maintenance view with open/all/completed/canceled filters, due dates/timezones/status text, pagination, source/history and links to the current target graph; point to Profiles for creation/correction rather than invent a second identity picker. Add Maintenance as a no-record page in contextual assistant page validation so the assistant remains available; no implied maintenance model write support. Use existing semantic colors and accessible controls; verify desktop/narrow light/dark and keyboard flow on synthetic records.

Portability/recovery: explicitly add task+revision projections to private exports, bump record format 3 and accept download formats 1/2/3, with ZIP manifest following current FORMAT. Preserve full correction/state history, unknowns, original IDs/dates and provenance. No extra account/auth/credential/job columns. Update current-format docs and assertions (not historic changelog contracts). Encrypted whole-installation recovery already includes tables; extend actual Linux recovery smoke to prove current task/completion and prior revision/source survived, plus two-owner privacy, originals and vault credentials. No raw personal import/restore or existing installation deployment.

Acceptance: meaningful RED service/UI tests before implementation, schema owner constraints and upgrade/downgrade preservation, two owners/guessed IDs/cursors, exact repeated/concurrent requests, changed replay, stale versions after correction/consolidation, rollback, completion/cancel/reopen/unknown dates, leap dates/invalid zones, timezone/DST/local midnight and clock reversal, deterministic dated/unknown pagination and bounded output. Sources and full history remain exact; exported format 3 includes only owner task history, ZIP and recovery preserve all relationships and typed dates. HTTP session/CSRF/strict body, MCP schemas/annotations/owner isolation. UI create/read/edit/complete/reopen, unknown/calendar dates, failed/stale/session/late responses and duplicate submissions. Real isolated browser lifecycle/reload/source/history at desktop and 390px in both themes, then full backend/frontend checks, wheel/build, code-only one-worker graph+HTML, fresh clash checks, reviewed exact-head source release and guarded clean-main image release/fresh-image recovery/remote tag verification.

Before coding, publish this bounded scope as the early feature branch commit under standing authorization. Refine routine details from tests/current source. No new dependencies, live provider requests, agents, Actions, package-visibility changes or real-data tasks/deletion/deployment.

Refined implementation choices before kickoff: keep maintenance state in the typed task/revision domain tables and source episodes; do not add redundant event entities or shadow graph-state assertions. The linked asset/place remains the ordinary graph record. Add original/current target metadata on reads; the source is searchable, while maintenance_get/list/history are the authoritative operational reads. This first increment does not claim Ask AI can plan or mutate maintenance.

Use a current-revision partial unique index and owner/task-bound previous-revision FK; flush superseding before inserting the new head. Revision recording time is monotonic max(clock, source, previous+1), including clock reversal. Create and revise have global owner-scoped revision request IDs and payload fingerprints; return original stable ack(id, revision_id) on an exact replay, even after later changes. A changed payload/type/target using the same request ID refuses. Revision/source/audit changes roll back together.

Date DTOs accept exact ISO calendar dates or explicit null, with a pre-validator rejecting numeric timestamps, datetimes, booleans and malformed/normalized date strings. Unknown due/completion choices are explicit in the form. Completed dates are allowed only in completed state; missing completion dates stay unknown. Per-task local date classification uses the stated IANA zone and injected server microsecond clock. Known due dates sort before unknowns; a base64url closed cursor binds scope/state/current last revision and due date/id, rejects foreign/cross-filter/stale anchors, and gives deterministic SQL keyset pagination. No task count or ordering claim beyond the actual returned page.

Global Maintenance is read-only with filters/open date ordering/source/history and a Manage in Profiles action. Add an initialEntityId prop to ProfilesPanel and keyed App navigation to the current canonical target; retain a selected-record option when it is outside the current entity picker page. Scoped forms live only in the selected ProfileEditor to avoid a second physical-identity picker. Maintenance is a no-record assistant page; no maintenance record context or model write tool is implied. Dedicated request handling must preserve HTTP409/401 classification rather than flattening errors through the existing generic profile request wrapper. Existing profile tests need an explicit empty maintenance fixture after the section is added.

## Final implementation and acceptance

The v0.55.0 implementation uses two typed private tables and one original source
per revision. User-facing evidence contains the linked record name, supplied
fields and exact statement; retry/version metadata remains in its database
contract. Every state change keeps history and preserves the original record ID.
Profiles initially shows all states, while the global Maintenance view defaults
to open tasks, so completed/canceled entries stay manageable from their links.

Complete-record comparison includes at most 20 current task revisions and their
source references. Task changes invalidate consolidation and reversal versions.
The empty comparison shape stays identical, preserving existing identity receipts;
consolidation recording time also follows its task revisions. No task state is
stored in a redundant event entity or graph JSON blob.

Verified acceptance:
- All 616 backend tests pass in 464.49s; final Ruff lint/format and strict mypy pass
  for 240 source/test/smoke files. The portability test additionally verifies that
  transcript deletion retains populated maintenance records and exact history.
- All 286 frontend tests across 51 files pass on the final build. TypeScript,
  frontend lint/format and production build pass. Tests cover explicit dates and
  unknowns, completion/cancel/reopen, stale drafts and explicit reload, lost-response
  identity, duplicate submissions, invalid responses, history/pagination and late
  profile/filter responses. Existing profile fixtures include the new empty read.
- Meaningful failing tests first reproduced missing maintenance services/UI and
  stale consolidation previews accepting new task records. The implementation
  fixes those gaps without loosening the expected owner or version boundaries.
- SQLite owner/previous-task/current-head constraints, failed-write rollback,
  concurrent requests, clock reversal, ISO/leap dates, DST/local midnight,
  private HTTP/MCP/session/CSRF, personal JSON/ZIP and upgrade/downgrade preservation
  all pass. Recovery accepts the previous 0023 schema and current 0024, and refuses
  missing current task tables/columns or a task without a current revision.
- An isolated real browser created an undated synthetic task, navigated through
  the global view to its correct profile, saved exact due/completion dates, reopened
  it and verified all three original revisions/sources through reload. Desktop
  light and 390px light/dark layouts have no horizontal overflow; keyboard task
  actions and form heading focus work. Test theme/dock/viewport were restored,
  own tab/server closed, and no real installation or provider was used.
- The wheel includes the service and migration 0024. Isolated read-only/non-root,
  no-network Linux source smoke preserves task completion, original unknown date,
  full revision/source history, originals, two owners and vault credentials through
  encrypted recovery of a 42.9 MB synthetic database. Fresh-image verification
  follows the clean-main image build after source merge.
- Code-only, single-worker Graphify extraction and HTML export completed with
  3,438 nodes /14,764 edges; no model calls, agents or automatic configuration changes.
  The extractor reports no symbols for migrations/env.py and ProfilesPanel.test.tsx;
  source compilation/tests remain authoritative.

Fresh GitHub checks find main 2767c774aadef5140f1b10f6ca6bae81ceaa8870 unchanged,
one checkout and no competing branch/PR or version/migration collision. Final
source delivery and guarded image publication use the standing authorization;
no existing installation is redeployed and no package visibility is changed.
