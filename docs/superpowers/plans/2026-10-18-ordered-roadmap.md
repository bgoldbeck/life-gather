# Ordered roadmap implementation plan

> Execute sequentially in the main/root chat using the planning and inline-execution
> skills. No agents. The user authorized continuous implementation, routine design
> decisions, and a separate commit/push/PR/merge/branch cleanup after every feature.

**Goal:** Complete the remaining personal-life organization roadmap in the agreed order.
**Architecture:** Preserve the private evidence store and framework-independent services;
extend existing authenticated HTTP/MCP adapters and responsive React views in bounded releases.
**Tech stack:** Existing Python/FastAPI/SQLAlchemy/Alembic/SQLite and React/TypeScript stack.
**Spec:** `../specs/2026-10-17-personal-discovery-design.md` and the user's ordered roadmap.

## Execution ledger and decisions

- The bundled v0.46.0 [contextual assistant](../../CONTEXTUAL_ASSISTANT.md) stays
  mounted across pages, docks/collapses, opens uniquely named assets from chat,
  and saves explicit profile details with original evidence and history. Ask AI
  gains owner-checked selected-record recall. External MCP context is explicit,
  with no ambient browser focus or live browser-control bridge.

- v0.46.0 adds [manual inventory entry on Assets](../../MANUAL_ASSETS.md), with
  original manual evidence, stated ownership and shared identity bindings. Later
  sources can enrich the same physical item; duplicate choices remain explicit.

- v0.45.0 adds [shared field history and workflow attribution](../../CHANGE_HISTORY.md)
  using the existing audit/fact store. The UI covers graph facts and preserves
  original sources, explicit correction links and unknown legacy origins. Custom
  asset templates and universal undo remain ahead.

- Protect unrelated edits and unfinished worktrees. No live personal-data ingestion,
  paid model calls or externally configured services without configured permission.
- Source delivery is authorized. Follow the standing source and GHCR release authorization in AGENTS.md; publishing
  never authorizes changing a running installation.
- Each feature receives meaningful failing tests, implementation, relevant full
  checks, self-review, version/changelog update, graph refresh and a merged PR.
- Record actual acceptance and remaining limitations; never equate a mocked adapter
  with a configured live connection or a source release with deployment.
- Ruling: include the dynamic version file in uv's cache key. A real version/package
  mismatch test caught stale editable metadata after the minor bump; watching the
  single version source fixes repeatable checks without manual reinstall workarounds.

## Ordered features

1. Appearance (merged, v0.10.0, PR #20): Light/Dark/System per authenticated user. Extend
   `user_settings` with migration `0011_appearance`; preserve external-AI consent.
   Add owner/CSRF-protected appearance reads/writes and include the current value
   in authenticated session metadata. React clears preference on sign-out, follows
   system changes, and applies semantic colors to all existing views. Test owner
   separation, migration defaults, invalid values, save failure and account switch.
2. Interactive graph (merged v0.11.0, PR #21): reuse existing `memory_related` and entity/source reads;
   bounded authenticated graph service/adapter, selectable accessible nodes and
   explicit edge evidence, empty/error/limit states, no fabricated relationships.
3. Home/vehicle profiles (merged v0.12.0, PR #22): sourced specifications and maintenance facts on existing
   private entities; preserve unknowns, evidence and time. No unverified fitment.
4. Richer chat: streaming and bounded read-tool orchestration; private persistent
   provider/model preferences, existing cancellation/usage/consent checks.
5. Google AI/Antigravity integration: verify official interfaces at execution,
   isolated credentials and fixed endpoints; no desktop subscription-token reuse.
6. Broader extraction: PDF/multi-item receipt input and typed quantities/prices/dates;
   untrusted parsing and reviewed evidence-backed candidates.
7. Automatic discovery: source-independent idempotent create/enrich/review with easy
   correction; never identify physical items from names alone.
8. Advanced duplicate resolution: reversible complete-record consolidation and
   explicit shipment/replacement/unit workflows, preserving conflicts/provenance.
   v0.37.0 adds reviewed cross-source purchase-evidence grouping with immutable
   move/withdraw history and exact canonical identity reuse. Automatic extraction,
   transaction allocation/refunds and whole-record consolidation remain ahead.
9. Photo handling: chat attachments, individual link removal, event galleries and
   graph navigation, preserving original privacy/deletion contracts.
10. Email connections and requested scans: owner-scoped credentials, requested scope,
    receipt discovery/reconciliation, no arrival-triggered ingestion.
    v0.34.0–v0.35.0 add separate Gmail consent and modular requested text-evidence
    imports. v0.38.0 adds optional requested/scheduled inline-text purchase discovery,
    inferred inventory reconciliation, durable extraction reuse and review/correction
    links. Attachments and conversational scan-start remain ahead.
11. Scheduled scans: durable timezone-aware jobs, progress, cancellation, recovery,
    deduplication, pause/edit and summaries.
    v0.36.0 implements private daily/weekly schedules through the shared runner,
    with DST, catch-up, overlap, revision protection and the existing result views.
12. Sourced requested web research: explicit scope and external-data permission,
    dated sources, no unsupported identity/ownership assertions.
13. Bank statements then live sync: deterministic exact-money tables and shared
    purchase reconciliation; verify service access/cost before configuring it.
14. User-facing export/backup/restore/privacy controls over the existing owner-scoped
    services, with clear scope and retention and tested recovery boundaries.
    v0.47.0 adds bounded consistent private JSON record downloads with history,
    exact money/units and file metadata. Original-file bundles and restore remain ahead.
15. Life management: independently verified warranty/insurance/maintenance/recall/
    consumable/subscription/timeline/dashboard increments with sourced records.
16. Additional sources: retailer exports, cloud files, contacts/calendar and home
    devices, each separately bounded and authenticated.

Dedicated mobile/PWA/share-menu and remote-access work remain explicitly deferred.
Specific file/interface/test plans for later features are refined from current
source immediately before that feature; do not prebuild speculative subsystems.

Graph verification: 163 backend tests and 50 frontend tests pass; Ruff, mypy,
TypeScript, frontend lint/format and production builds pass. Graphify refreshed
1389 nodes / 5002 edges; its existing partial AssetsPanel extractor warning remains
(the TypeScript compiler passes). No migration or Docker deployment.

Profile scope: existing asset/place details plus explicitly separate home/vehicle
creation, exact sourced text, stated/inferred/unknown status, optional valid dates,
immutable correction history, private MCP inspection and graph navigation. Original
photo evidence can still be attached through asset photos; live VIN/fitment lookup
and automatic maintenance reminders remain later work. No schema change.

Profiles verified: 166 backend tests / 52 frontend tests, Ruff lint/format, mypy,
TypeScript, frontend lint/format, Vite and wheel builds pass. Isolated browser QA
created a synthetic home, saved a sourced paint detail and followed it into the
graph. No real records, model calls, migrations or Docker changes.

Feature 4 is delivered in bounded releases: 4a saved provider/model choices
(v0.13.0), 4b streaming replies, 4c bounded read-only tool orchestration. Preferences
are explicit, owner-scoped and never imply permission to contact a provider.
Migration 0012 adds only a private preference table; removing a connection clears
the effective choice rather than selecting a different provider.

Chat choices verified: full backend suite 167 passed, followed by both preference
tests (including the newly added upgrade-preservation test) passing; frontend
53 passed, all lint/type/format checks and builds pass. Graphify refreshed
1461 nodes / 5178 edges. No provider calls or Docker publication.

4a merged v0.13.0 via PR #23. 4b streaming implementation: direct bounded SSE
adapters for OpenAI and Claude, shared transient JSON-text preview, private POST
transport, explicit draft labeling and validation before persistence. Final schema
and citations still gate the durable reply. Disconnects cancel only the fresh
request, preserving retry identities and completed responses. No schema change.

Streaming verified: 172 backend / 56 frontend tests; lint, types, formatting and
production builds pass. Tests cover byte-split provider events, partial JSON escape
boundaries, truncated streams, invalid citations, safe replay and cancellation.
No live provider calls or Docker deployment.

4b merged v0.14.0 via PR #24. 4c bounded read orchestration: the existing plan
chooses up to two exact names and optional direct connections. Host executes the
same private domain contracts as MCP; no model SQL/writes, extra planning call or
unbounded loop. Preserve complete literal values, provenance, corrected-source
metadata and ambiguous distinct records; cap total context and link replies to
the graph. Version v0.15.0, no migration.

Record recall verified: 174 backend / 56 frontend tests, all lint/type/format
checks and builds pass. Coverage includes private ownership, same-name ambiguity,
corrected sourced values, bounded context, private MCP lookup and reply graph links.
No live calls, migrations or Docker changes.

4c merged v0.15.0 via PR #25. Feature 5: Google Gemini Interactions adapter
(v0.16.0), shared private credentials/consent/usage, structured output/streaming
and sanitized photo input. Current official Antigravity agent docs explicitly
exclude structured outputs and max_output_tokens; defer that managed-agent
runtime rather than weaken the current bounded contract. This is a recorded
technical limitation, not an implemented Antigravity integration. No live calls.

Google Gemini verified: 182 backend / 57 frontend tests, lint/type/format checks
and production builds pass. Tests cover fixed stateless requests, private header
keys, image input, thought exclusion, streaming, redacted failures, consent, saved
choices and no provider fallback. Graphify refreshed 1572 nodes / 5433 edges.
All Google testing is mocked; Antigravity managed-agent support remains deferred.

Feature 5 Gemini merged v0.16.0 via PR #26; managed Antigravity remains explicitly
deferred. Feature 6 is split into 6a private PDF originals/reviewed text (v0.17.0)
and 6b multi-item typed receipt extraction. PDF text is untrusted and requires
review before memory capture. Original links survive corrections/deletion as
metadata; deletion retains reviewed source history. Migration 0013 and pinned
pypdf 6.21.1. Separate parser process, bounded bytes/pages/text/decompression/time;
Linux resource limits are implemented but not executed on this Windows host.

PDF evidence verified: 190 backend / 58 frontend tests, lint/types/format checks
and builds pass. Coverage includes owner isolation, exact original downloads,
CSRF, idempotent uploads/review, corrected-source links, deletion retention,
parse timeout, decompression caps, truncation and private MCP reads. Graphify
refreshed 1650 nodes / 5715 edges. No external calls or Docker changes.


Receipt increment v0.19.0 implements bounded multi-item extraction and sourced
quantities, explicit per-unit new/link decisions, atomic batch review, private queue
integration, source correction/deletion guards and safe request replay. See
`../../MULTI_ITEM_RECEIPTS.md`. This is partial feature 6b: typed monetary values,
purchase dates and accounting remain deferred. No automatic ingestion or live AI
verification. Migration 0014 adds private receipt drafts; no new dependency.

Receipt verification: 201 backend tests / 68 frontend tests; Ruff, mypy, TypeScript,
frontend lint/format and production build passed. Synthetic browser QA followed
Memories → Chat → persisted Review and confirmed three physical units together.
Graphify executable is unavailable in this environment; graph/HTML refresh could
not run. Source and tests were inspected directly. No real provider call.


Purchase-detail increment v0.20.0: explicit human-entered USD line totals and
purchase dates for confirmed purchased receipt lines. Exact labeled source quotes,
integer cents, world/recorded time separation, immutable corrections/withdrawal,
private HTTP/MCP, current-revision concurrency guard and lost-response replay.
Migration 0015 preserves accepted receipts. This is bounded feature 6b progress;
automatic price/date extraction, other currencies and accounting stay deferred.

Purchase details verified: 225 backend / 72 frontend tests; Ruff lint/format, mypy,
TypeScript, Oxlint, Prettier, frontend build and source/wheel builds pass. Tests
include immutable withdrawal, exact cents including zero and upper bound, concurrent
retry, stale-head conflicts, invalid dates/quotes, owner/CSRF/MCP boundaries, deleted
PDFs, snapshot restore and upgrade from confirmed v0.19 receipts. Synthetic browser
QA saved/reloaded the line total/date with source passages. Fixed recorded-time
display to convert stored microseconds correctly, with a regression assertion.
Graphify is unavailable; graph/HTML refresh could not run. No external AI calls.

## v0.21.0 — exact receipt-detail suggestions and source badge

Bounded plan: expose no-write suggestions through existing owner-scoped purchase
reads, copy uniquely labeled USD line totals from the item's own printed line and
one real ISO purchase date, then let users explicitly copy/review/save the draft.
Reuse existing validation, CSRF, immutable revisions and replay; no new schema,
model request or inventory behavior. Ambiguous values remain unknown. Add a README
source-version badge linked to CHANGELOG and enforce version synchronization.

Preflight: purchase reads supply the UI and MCP; additive suggestions preserve
existing consumers. Save still validates source availability and revision head.
Root-only implementation and self-review respect the user's no-agent rule.
Tests observed failing before implementation: missing suggestions keys (three
backend cases), missing draft-copy button, missing README source-version badge.

Verified v0.21.0: 229 backend / 73 frontend tests pass, Ruff lint/format,
mypy, TypeScript, Oxlint, Prettier and wheel/frontend builds pass. Self-review
confirmed additive read output, no automatic writes, stable revision checks and
no source/model permission changes. Graphify refreshed 1792 nodes / 6813 edges and
HTML; its pre-existing partial AssetsPanel extraction warning is covered by the
passing TypeScript build. No migration, live provider call or Docker change.

## v0.22.0 — explicit receipt currencies

Bounded plan: extend existing typed claims and source suggestions to printed
USD/EUR/GBP/CAD/AUD/JPY; exact integer minor units, no conversion or rounding.
Use whole yen for JPY, two decimals otherwise. Add a currency selector and retain
exact source validation. Migration 0016 replaces only the currency constraint,
preserving every old revision/index and rejecting lossy downgrade. Preserve old
USD request fingerprints so upgrading cannot break a lost-response replay.

Preflight: schema, domain reader/writer, MCP typed schemas and receipt UI share
DetailSave; default USD is backward compatible, explicit non-USD is source-checked.
Observed failing tests: missing currency suggestions, rejected currency input and
missing frontend currency selector before implementation. Existing history/privacy,
source correction and retry tests remain required. Root-only self-review.

Verified v0.22.0: 250 backend / 74 frontend tests pass; Ruff lint/format,
mypy, TypeScript, Oxlint, Prettier and production/wheel builds pass. Tests cover
exact values, source/currency mismatch, invalid precision/exponents/signs,
ambiguous currencies, migration preservation, legacy replay and lossless-downgrade
refusal. Self-review confirmed the unchanged owner/source/revision gates and
no floating point. Graphify refreshed 1806 nodes / 6865 edges and HTML. Migration
0016 only; no provider call, image build/upload or running-container changes.


## v0.23.0 — individual photo attachment correction

Order decision: finish a small correction prerequisite before enabling broader
automatic discovery. Remove one photo/asset gallery binding, preserving originals,
other galleries and claim evidence. Reuse owner/session/CSRF adapters and photo
version guards; no new schema. Audit both stable IDs. An absent link is safe replay;
a reattached link changes the photo version, so an old request cannot remove it.
The UI explains retention and reattachment through existing deduplicated upload.

Observed failing tests for the missing service operation and UI action. Added
owner/CSRF/MCP checks, multi-gallery preservation, original bytes, no duplicate
audit on retry, stale reattachment protection and exact UI request checks.
Root-only implementation and self-review, no delegated work.

Verified v0.23.0: 253 backend / 75 frontend tests pass; Ruff lint/format,
mypy, TypeScript, Oxlint, Prettier and wheel/frontend builds pass. Self-review
found the new JSON action missing from request-size middleware; a regression test
failed (401 rather than bounded 413), then passed after adding the route prefix.
Full backend suite rerun after the fix. Graphify refreshed 1829 nodes / 6821 edges
and HTML. No migration, provider call, Docker publication or deployment.


Purchase browsing increment v0.24.0 closes the discovery gap in v0.20: optional
receipt claims now appear on the currently linked physical asset, with direct
source and receipt editor/history links. Bounded five-line HTTP/read-only MCP
pages follow active reconciliation bindings, including reassignment, dismissal
and undo. Unknown/withdrawn values and historical-source warnings remain explicit;
whole line totals are never converted to unit prices or combined across receipts.
No migration, dependency or AI recall expansion. Automatic discovery remains the
next broader phase; this increment makes the completed receipt feature usable.


Integrated asset purchase browsing verified against main 5309fa2: 259 backend /
78 frontend tests; Ruff lint/format, mypy, TypeScript, Oxlint, Prettier, Vite and
source/wheel builds pass. Preserve newer receipt suggestions, explicit currency
precision and photo-link correction. Extra EUR/JPY association tests pass; synthetic
browser QA shows EUR 49.90 unchanged on the linked physical unit. Feature itself
adds no migration or model call. Graphify remains unavailable, so graph/HTML refresh
could not run. Version advanced to 0.24.0 after concurrent v0.21–0.23 merges.


Reviewed purchase recall v0.25.0 closes the Chat gap left by asset purchase browsing:
use current owner-scoped receipt links, latest detail revisions, exact currency,
whole-line scope, withdrawal/historical flags and source citations. Bounded to two
records / three receipt lines each under the existing byte budget and two-call
provider flow. Receipt-source markers prevent missing/omitted reviewed details
being replaced by stale raw totals in answer instructions. Shared source labels
fix photo/PDF provenance on named-record recall. No new schema/dependency/tools.
Automatic discovery remains the next broader phase after this receipt-loop fix.

Purchase recall verified: 265 backend / 78 frontend tests; Ruff lint/format, mypy,
TypeScript, Oxlint, Prettier, frontend and source/wheel builds pass. New coverage
checks latest/unknown/withdrawn details, keyword-only receipt markers, byte-budget
omissions, exact EUR/JPY precision, current association changes, deleted photo/PDF
provenance and cited two-call replies. Synthetic browser used reviewed EUR 49.90
for two distinct units and opened its original citation. No real provider calls;
answer instruction following remains unverified against a live model. Graphify is
unavailable, so code graph/HTML refresh could not run. No migration or dependency.


Automatic-discovery slice v0.26.0: explicitly reviewed single-item proposals can
create/enrich when the deterministic matcher is clear. Names/weak identity,
conflicts, excluded ownership and conflicting serial history remain pending with
preserved edited fields and candidate comparison. Atomic existing review contracts,
stable retries and source evidence retained; deleted-PDF single-proposal acceptance
is fixed. No unattended AI writes, batch auto-import, migration or dependency.

Clear-item discovery verified: 272 backend / 81 frontend tests; lint, types, format,
production frontend and source/wheel builds pass. Browser QA recorded a synthetic
reviewed purchase through the automatic identity action and cleared the queue.
Tests cover concurrent replay, ambiguity without derived writes, unique serial
enrichment, sold/conflicting serial refusal, stale/deleted PDF sources, private
HTTP/MCP and stable UI retries. Graphify unavailable; graph/HTML not refreshed.


Candidate comparison v0.27.0 improves ambiguous discovery decisions: explicit
read-only, two-record source/identifier/correction snapshots in all three review
flows. Existing bounded owner-scoped asset reads only; no eager fetch, automatic
selection, merge or write. Candidate buttons page by five; late/closed reads are
canceled/ignored. Explicit identity review remains required. No migration/API/tool.

Comparison verified: 272 backend / 84 frontend tests; lint, format, types, frontend and source/wheel builds pass. Synthetic browser compared distinct serials S1/S2, showed sold ownership correction, opened its exact evidence and preserved the unselected identity choice. Graphify unavailable; graph/HTML refresh could not run. No schema/dependency/security boundary changes.


Unit correction v0.28.0: bounded phase-8 increment moves one current multi-unit
binding to an explicit existing target; keeps sibling unit order and mappings,
preserves decision/source history and typed line-total meaning. Reject duplicate
targets, stale/foreign/missing mappings. No whole-record consolidation, mixed new
unit creation or single-unit undo of a whole receipt. Existing atomic service and
HTTP/MCP contracts, no migration/dependency.

Unit correction verified: 276 backend / 86 frontend tests; lint, format, types, frontend/package builds pass. Coverage includes typed whole-line money, exact sibling mapping, explicit reversal, private HTTP/MCP, stale sibling races, rollback after derived writes and snapshot recovery. Browser moved unit 2 and verified its receipt on the target; fixed stale purchase cards after corrections. Graphify unavailable; graph/HTML refresh could not run. No migration or dependency.


Automatic receipts v0.29.0: explicit per-line automatic identity from reviewed
fields and purchase/possession. Entire selected batch creates/enriches only when
clear; ambiguity returns fresh comparisons without writes/consuming request id.
Cross-line identity changes roll back atomically. Manual new/link/skip remains;
no partial draft state, unattended ingestion, money extraction or schema/dependency.

Automatic receipt verification: 283 backend / 88 frontend tests; lint, format, types, production frontend and package builds passed. Coverage includes concurrent exact replay, ambiguity with no sources/entities/facts/audit writes, active serial enrichment, sold refusal, cross-line rollback, corrected sources, private HTTP/MCP and lost-response retry. Synthetic browser kept ambiguity pending, opened its candidate and completed a mixed automatic/manual three-unit receipt. Graphify unavailable; graph/HTML refresh could not run. No migration/dependency.


Inventory correction v0.29.1: share current-world ownership predicates for the
asset screen, discovery/MCP inventory and automatic matching. Exclude sold/returned/
no-longer-owned current statements before paging; preserve historical bindings.
Finite active intervals block enrichment; future/ended statements do not. Explicit
buyback restores inventory. No schema, dependency or UI change.

Inventory consistency verified: 293 backend / 88 frontend tests; lint, format, types, frontend and package builds pass. New coverage checks sold/returned/no-longer-owned exclusion, buyback, preserved history, current/future/ended intervals, inclusive starts/exclusive ends and private MCP pagination. Graphify unavailable; graph/HTML refresh could not run after shared predicate extraction. No schema/dependency/UI change.


Evidence-move inspection v0.30.0: exact selected source, distinct decision/target
IDs, source/target candidate comparison, and new-search target reset. Incoming
correction history reads preserve the separate own-action write head; new actions
retain actual created targets. Old targetless new-item actions remain on original
history without speculative backfill. No migration/dependency/general consolidation.

Evidence-move inspection verified: 295 backend / 90 frontend tests; lint, format, types, frontend and package builds pass. Tests cover incoming private HTTP/MCP reads/cursors, own write heads after incoming moves, actual new targets, exact source opening, nonselecting comparisons and hidden-target search reset. Browser compared source/target, moved a receipt unit and opened receiving correction with both names. Graphify unavailable; graph/HTML refresh could not run. No migration/dependency.


Navigation correction v0.30.1: preserve the current asset intent when earlier
reloads, saves or pagination complete late. Guard detail reload, list/history pages,
errors and loading completion by the active request generation; avoid starting an
old item's reload after the user has already moved on. Invalidate work on view
change/unmount. No domain/API/migration/dependency change.

Navigation verification: 296 backend / 95 frontend tests pass; lint, format, types, frontend/package builds pass. Five UI regressions cover late reload/save completion, stale list/history pages and loading-state recovery. Delayed synthetic browser stayed on Saw after the previous Drill reload. Added a composed receipt/JPY/unit correction/sale/recall/private snapshot-restore regression for this session's lifecycle. Graphify unavailable; graph/HTML refresh could not run. No migration/dependency/domain API change.


Reload feedback correction v0.30.2: catch manual correction-form reload failures,
preserve draft fields and show a safe retry. Freeze the form during its reload;
never submit a correction merely to reload. Navigation guards and completed-write
retry identities remain intact. No domain/API, migration or dependency change.

Reload feedback verified: 296 backend / 96 frontend tests; lint, format, types and production/package builds pass. Regression checks failure feedback, preserved draft, successful retry and no write; existing delayed-navigation regressions still pass. Browser simulated a 503 reload failure and recovered with the unsaved statement/explanation intact. Graphify unavailable; graph/HTML refresh could not run. No migration/dependency/domain API change.


Discovery-evidence batches v0.31.0: explicit preview/apply of all 1–5 current
associations to one existing item, atomic stale/collision refusal, exact sibling
unit mappings, append-only explanations and unchanged-batch reversal. Manual
facts, notes, photos, aliases and relationships stay on their original records;
whole-record consolidation remains ahead. No schema/dependency/live-provider change.

Verified: 305 backend / 101 frontend tests; lint, format, types and production/
package builds pass. New coverage checks concurrent exact replay, transaction
rollback, owner/CSRF HTTP/MCP guards, snapshot reversal, stale source/target/
evidence refusal, five-observation twenty-unit Unicode limits, preview source
inspection, lost-response retry and saved-write reload recovery. Synthetic browser
moved two associations and restored both, preserving USD 49.90 whole-line meaning
and receipt unit 1 of 2. Graphify unavailable; graph/HTML refresh could not run.


Sourced replacement links v0.32.0: explicit existing original/replacement item
choices, explained stated graph assertion and optional known event date; private
incoming/own history and unchanged-latest-link withdrawal. Preserve all receipt
units, typed amounts and explicit ownership, including sold/returned states.
No identity merge, ownership inference, migration, dependency or provider change.

Verified: 313 backend / 106 frontend tests; lint, format, types and production/
package builds pass. Tests cover exact/concurrent replay, competing requests,
source/target owner guards, HTTP/MCP/CSRF, snapshot recovery, historical dates,
corrected-fact withdrawal refusal and atomic failed writes/withdrawals. Browser
created the sourced graph edge and withdrew it while preserving the original
statement and USD 49.90 line claim. Fixed an observed appearance-test timing race
by awaiting the existing asynchronous theme effect. Graphify unavailable, so
source graph/HTML refresh could not run. Whole-record consolidation remains ahead.


Correction recall v0.32.1: bounded named-asset own/incoming history and canonical
inferred inventory membership independent of keyword matches; correction source
metadata identifies superseded ownership/replacement and changed association
versions. Incoming keyword lookup includes either linked item and preserves
separate origin/target pairs. Current purchase bindings and original text remain.
No new provider call, migration, dependency or model write capability.

Verified: 319 backend / 109 frontend tests; lint, format, types and production/
package builds pass. Coverage includes moved/reversed receipt associations,
separate incoming targets, buyback history, withdrawn replacement dates, private
HTTP/MCP source metadata, context byte/source caps and cited two-call answers.
Synthetic browser asked about a withdrawn link, cited incoming correction history
and opened its historical-state label. No live provider call; actual model
instruction following remains unverified. Graphify unavailable; graph/HTML not refreshed.


Private photo reuse v0.33.0: deliberate five-item paged chooser links an existing
private original into another physical item gallery, without file reupload or AI.
Expected-version checks, harmless existing-link retries, stale removed-link and
deleted-original refusal; coordinate gallery controls and preserve other galleries,
receipt bindings, exact amounts, ownership and claim evidence. New attachment audit
entries retain both IDs. No schema/dependency/original-deletion policy change.

Verified: 323 backend / 120 frontend tests; lint, format, types and production/
package builds pass. Tests cover concurrent link replay, one retained binary,
owner/CSRF HTTP/MCP and body limits, no fact/entity writes, rollback, snapshot
recovery, stale/deleted requests, loss/reload retries and parent-gallery refresh.
Browser linked, removed, refused stale reattachment and deliberately reattached a
synthetic original after refresh. Fixed stale parent removal feedback after relink.
Graphify unavailable; source graph/HTML refresh could not run. General record
consolidation, chat photo picking and event galleries remain separate work.

Photo gallery regressions additionally cover delayed initial metadata after an
upload, stale transcription success/error after selection, evidence-close intent
and old pagination after a fresh upload reload. These reads now respect request
generations and unmounts; no original data or correction is changed.


Chat evidence navigation v0.33.1: source/conversation generation guards preserve
closed evidence and the current conversation when older pages or errors arrive.
A prior read cannot clear a newer source's loading state. Conversation changes
clear old receipt and asset review panels; drafts and completed records remain.
No domain API, migration, dependency or provider change.

Verified: 324 backend / 126 frontend tests; lint, format, types and production/
package builds pass. Six Chat regressions cover late source success/error after
new conversation, navigation with a newer read, close-during-page intent and both
review panels across new/existing conversation changes. A composed backend
regression joins this session's batches, photo reuse, replacement withdrawal,
strict reversal refusal, explicit unit recovery, bounded private recall and
snapshot replay. Browser used a four-second delayed citation and retained the
new-conversation view after completion. Graphify unavailable; graph/HTML not refreshed.


## Worktree reconciliation, 2026-10-18

GitHub main through v0.33.1 (`f300368`) supersedes the older unfinished receipt and
private-chat drafts. Preserve those drafts and their original commits in local
recovery snapshots/archive refs; do not merge them into main. The unfinished local
v0.24.0 label is not a release: merged v0.24.0 is purchase-record inspection.

Keep the merged v0.29 automatic receipt behavior: if any automatic identity is
uncertain, retain the entire receipt pending without partial graph writes. The
older draft's partial-create-plus-identity-queue behavior is not adopted. Current
source already contains single-item/receipt automatic matching, PDF deletion
guards, candidate comparisons, unit corrections, purchase recall, batch evidence
moves, replacements, photo reuse and navigation fixes. Follow current acceptance
and tests before choosing the next missing milestone.

Three dirty historical worktrees were snapshotted with raw-file SHA-256-verified
ZIPs and protected Git recovery refs. Original branches were renamed locally to
`archive/2026-10-18/*`; no unmerged commits were deleted or published. Their
checkouts and local main were aligned to the merged baseline, preserving ignored
local files. Both unrelated main documentation edits were hash-checked unchanged.
Recovery archives remain outside the repository; no private draft data is published.

Add repository baseline checks at start/resume and before delivery to prevent
repeating work from stale summaries/worktrees. This is development maintenance,
not an application feature; retain v0.33.1 and make no image/deployment changes.


Reconciliation verification: the merged baseline's full 324 backend / 126 frontend
tests passed. Strict mypy from backend then exposed ten pre-existing test-only
errors in five files: an untyped helper, widened export-table keys and nullable
source context indexing. Add explicit domain annotations, literal table names and
non-null assertions without weakening checks or changing production behavior.
Strict mypy and Ruff pass after those fixes; all 33 tests in the affected modules passed.
Use the backend working directory so future type checks load its strict config.
Frontend lint/types/format and production build also pass. Refresh the local source
graph/HTML against the reconciled code, rather than trusting the old graph cache.

The reconciled local Graphify graph/HTML contains 2107 nodes / 8234 edges. Recovery ZIPs, all three protected refs and both unchanged user-edit hashes were reverified before delivery. Self-review confirmed only test annotations/assertions and workflow documentation changed; no production code, migrations, version bump or Docker operations.

Correction chronology v0.38.1: after fetching and inspecting current GitHub main,
preserve all v0.34–0.38 mailbox, scan, schedule and purchase changes. Batch
move/restore explanations and audit times cannot precede their changed decisions;
individual reassociation/undo use one explanation/decision/audit transaction time.
Five regressions reproduced the defects; historical reads, exact replay, sibling
units and snapshot recovery pass. Full verification: 390 backend / 138 frontend,
lint/format/types and package/frontend builds; twelve offline publisher cases pass.
No new migration, dependency, live provider call or deployment. Graphify is not
installed in this environment; source graph/HTML refresh could not run.

Current-record comparison v0.39.0 adds explicit owner-scoped inspection of two
records in one read snapshot: statement evidence/relationships, aliases, photo
metadata, discovery units, receipt line claims and unique purchase evidence.
Preserve dates/status/unknowns and exact amounts; flag conflicts and distinct units.
Refuse incomplete collection/byte-bounded results rather than present a partial
preview as complete. This is read-only inspection, not consolidation or a merge
authorization. Verification: 410 backend / 145 frontend, lint/format/types and
package/frontend builds; desktop/narrow browser and synthetic lifecycle checks.
Fixed existing photo-grid minimum width during 390px QA. No migration/dependency/
provider call/redeploy. Graphify unavailable; source graph/HTML not refreshed.

Saved photo Chat v0.40.0: explicit private five-item paged picker and existing
photo extraction in the chosen conversation, with original evidence and human
proposal review. Preserve text drafts and consent/model/budget gates; retain exact
pending/lost-response retry identities and do not call completed writes uncertain
when usage refresh alone fails. Reset choices/reads on every conversation intent.
Verification: 411 backend / 159 frontend, lint/format/types and builds; synthetic
private conversation/vision/replay test, browser source/proposal inspection and
390px layout without overflow. Existing Chat grid/row minimum width fixed during QA.
No migration, dependency, provider-adapter change or live call/redeploy. Graphify
unavailable; source graph/HTML not refreshed. Uploads and multi-item photo receipts
remain separate from this saved-photo increment.

Chat background read intent v0.40.1: all eight new delayed-read regressions pass; full verification
411 backend / 167 frontend tests, formatting/lint/strict types and package/frontend
builds pass. Synthetic browser: save completes and New conversation works while
usage is delayed eight seconds; late refresh leaves new context intact. No domain,
API, migration, dependency or provider changes. Graphify is unavailable locally;
source graph/HTML refresh could not run. No live calls or running-app deployment.

Direct Chat upload v0.41.0: explicitly save one private JPEG/PNG/WebP original
(up to 8 MiB), then separately request the existing photo reading/review. Preserve
text drafts, configured provider permissions and active-original hash reuse;
freeze uncertain upload inputs and discard callbacks after context changes.
Deduplicate uploaded originals in later library pages. Verification: 412 backend /
181 frontend, strict types including tests, lint/format and both builds, synthetic
browser upload/explicit reading and narrow layout, HTTP/private/recovery smoke.
One earlier comparison test Literal annotation corrected. No schema, API,
dependency, provider-adapter or live call/deployment change. Graphify unavailable.
Multi-item photo receipts and arbitrary image questions remain ahead.

Multi-item receipt photos v0.42.0: explicit Chat photo action, one unverified
transcription plus bounded validated draft in one transaction, existing reviewed
quantities/units and original photo links. Reuse existing reviews/current text
without overwriting sources; active single-item review must be resolved first.
Photos can reopen saved receipt review. Tighten cropped-quote quantity validation
for pending receipts while preserving accepted history. Pre-merge verification:
434 backend / 188 frontend, strict source/test types, lint/format/builds; synthetic
browser confirms three units and blank money, composed replay/recovery smoke.
No migration/dependency/provider-adapter/live-call/redeployment change. Graphify
unavailable. New Chat mode extract_photo_receipt; existing modes remain supported.

Chat email evidence scans v0.43.0: explicit mailbox/date/query/message scope,
atomic durable queue and saved Chat result, safe replay and interrupted-pending
recovery without AI. Cancellation before enqueue creates no job; queued jobs use
Scans cancellation. Preserve text drafts and context resets; open/focus the exact
private job from Chat. First scope is original email text only, not AI purchase
discovery or attachments. Verification: 446 backend /195 frontend tests, with
22 affected backend cases rerun after the pending-recovery adjustment; strict
types, lint/format and package/frontend builds. Synthetic browser import, saved
conversation/result/evidence navigation and 390px form pass. Queue/worker/replay/
snapshot smoke uses synthetic transport. No schema/dependency/provider-adapter/
live-call/redeployment change. Graphify unavailable; graph/HTML not refreshed.

Private record export v0.47.0: explicit Settings download, one SQLite snapshot,
23 frozen owner-scoped collections, original/correction history, audit origins,
exact reviewed money and distinct units, chat and file metadata. Credentials,
authentication/configuration/processing caches and binary originals are excluded;
this is not a restorable backup. Refuse above 10,000 rows or 16 MiB without partial
files. UI validates format/safe filename, handles failures and abandons late reads.
Reconciled onto current main 3d5a1c3 including migration 0022/manual assets/contextual
assistant. Verification: 479 backend /222 frontend, strict types/lint/format/builds,
actual synthetic browser download (45 records, 23 collections, 18 audit origins),
390px with the dock, standalone quantity/JPY/history/privacy/snapshot smoke.
No new migration/dependency/provider call/deployment. Graphify unavailable locally;
graph/HTML refresh could not run. Linux smoke and source/GHCR release follow.
