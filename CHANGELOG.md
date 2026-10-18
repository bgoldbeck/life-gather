# Changelog

## 0.31.0 — Review and reverse discovery-evidence batches

- Preview all 1–5 current discovery associations before explicitly moving them
  to one existing physical item. Preserve other receipt units, exact original
  sources, typed purchase claims and the earlier decision history. Refuse the
  entire operation if the preview changes or two receipt units would collide.
- Reverse an unchanged batch with one explained action; stale item corrections
  or changed associations prevent reversal. Exact retries remain idempotent,
  including after snapshot recovery. Private HTTP and MCP share the same service.
- Notes, photos, aliases, manual facts and relationships stay on their original
  records. This is evidence movement, not whole-record consolidation. Preview
  passages are bounded excerpts with source links; browse history uses summaries.
- No schema migration, dependency or live-provider change.

## 0.30.2 — Recover from failed correction-form reloads

- Catch manual item-reload failures and show a retryable message while preserving
  the correction draft. Prevent edits or writes during that reload, clear the
  error after successful retry, and keep completed-write retry behavior unchanged.
- Reloading never submits a correction. No domain/API, migration or dependency change.

## 0.30.1 — Keep asset navigation stable during slow requests

- Ignore old reload and correction-completion callbacks after the user selects
  another item. A late response cannot reopen the previous record.
- Guard asset-list and correction-history pagination against graph navigation,
  selection changes and unmounts. Stale pages, errors and loading completions cannot
  replace the current view or append another item's history.
- Preserve completed corrections and existing safe retry behavior. No backend
  domain/API, migration, dependency or provider changes.

## 0.30.0 — Inspect evidence moves and receiving history

- Show the exact selected decision passage and its source before a correction.
  Distinguish decisions and targets by record ID and unit; compare source/target
  evidence without selecting or merging items. A new search clears old targets.
- Show incoming reassociation explanations in the receiving item's correction
  history with private pagination and original/receiving names in source context.
  Incoming reads preserve each item's independent correction write-version chain.
- Retain actual newly created targets on new correction actions so their receiving
  history is discoverable. Older new-target actions without target metadata are
  unchanged; they remain accessible on the original item's history. No migration,
  dependency, provider call or automatic whole-record consolidation.

## 0.29.1 — Keep current inventory and matching consistent

- Exclude valid negative ownership statements from reconciliation/MCP discovery
  inventory, matching the asset screen. Apply exclusions before pagination; retain
  original bindings and history. An explicit buyback restores current inventory.
- Share current-world ownership predicates across Assets, discovery inventory and
  identity matching. A negative interval blocks automatic enrichment while valid;
  future or ended intervals do not. Start dates are inclusive and end dates exclusive.
- Preserve owner isolation, explicit corrections and evidence. Discovery inventory
  remains limited to discovery-bound assets. No migration, dependency or UI change.

## 0.29.0 — Record clear reviewed receipt identities together

- Add an explicit automatic-identity choice per reviewed receipt line. Fresh
  deterministic identity checks create clear new units or enrich reliable active
  identifiers without asking the user to select a redundant target.
- An ambiguous automatic choice leaves the entire receipt pending with fresh
  candidate comparisons and preserved edited fields. No partial graph writes or
  consumed retry identity. Matching names never identify physical items.
- Preserve selected/excluded lines, explicit purchase/possession, exact source and
  quantity validation, atomic concurrency and safe retries. Cross-line identity
  changes roll back the batch and require manual review. Accepted results label
  automatic decisions. No migration, dependency, provider call or unattended import.

## 0.28.0 — Correct one receipt unit without moving its siblings

- Move one physical unit from a multi-unit source line to an explicitly chosen
  existing item. Other unit targets, ordinals and source history are preserved.
  Purchase details follow current unit associations without dividing line totals.
- Reject duplicate unit targets, missing/foreign targets, stale sibling decisions
  and whole-line undo through this single-item form. Reversal is an explicit
  move back using the current decision; stable retries return their original result.
- Display this item’s unit number in asset history and correction choices. Single-unit
  creation/undo keeps its existing behavior. Atomic owner-scoped HTTP/MCP service;
  no migration, dependency, provider call or general record consolidation.

## 0.27.0 — Compare ambiguous physical items before choosing

- Add read-only candidate inspection to single-item proposals, receipt-line review
  and identity review. Compare two records side by side, including sourced
  manufacturer/model/serial passages, current inventory status and latest corrections.
- Open exact observation/correction evidence without selecting or merging items.
  Page five candidate buttons at a time; load only on request using existing
  authenticated, bounded asset reads. Closed/evicted requests are canceled and late
  responses cannot replace a different comparison. Errors support retry.
- Keep final identity selection explicit and preserve all review/source guards.
  No migration, backend API/tool, dependency, AI call or graph write added.

## 0.26.0 — Record clear reviewed items automatically

- Add a one-action identity decision for reviewed single-item proposals: record a
  clear new item, enrich a unique active serial identity, or leave ambiguity pending
  with its candidate comparison. Similar names never merge physical items.
- Preserve source evidence, explicit reviewed purchase/possession, atomic replay,
  current ownership corrections and conflicting/historical serial review gates.
  Automatic decisions are labeled; manual same/different review stays available.
- Fix single-item PDF proposals accepting evidence after original-file deletion;
  both manual and automatic acceptance now refuse, while rejection/history remain.
  No migration, dependency, provider call, new tool or background ingestion.

## 0.25.0 — Reviewed purchase recall in Chat

- Include up to three currently linked receipt lines per matched asset in bounded
  read-only Chat recall, using the same owner-scoped service as Assets. Preserve
  exact currencies, whole-line quantities, latest revisions and withdrawn unknowns.
- Mark receipt sources so absent/omitted reviewed details cannot be silently
  replaced by older raw totals. Label historical corrected/deleted sources and
  retain citations; never infer unit prices, combine currencies or sum duplicate
  receipt-line appearances across physical units.
- Fix named-record recall that lost photo/PDF provenance unless keyword search
  independently found the same source. Share source labels across both paths.
  No extra provider call, schema change, dependency or write/model tool.

## 0.24.0 — Purchase records on asset details

- Show linked receipt lines, latest currency-preserving totals/dates,
  exact quotes and
  recorded revisions directly on each physical asset. Open original source or the
  receipt editor/history without searching old conversations. Refresh summaries
  after editing; unknown and withdrawn values remain explicit.
- Follow current reconciliation bindings rather than the receipt's original
  acceptance result, so reassignment/dismissal and undo update the correct item.
  Flag corrected/deleted originals as historical sources; preserve source evidence.
- Add bounded, owner-scoped HTTP and read-only MCP receipt-link pagination. Whole
  line totals are never presented as per-unit prices or combined across receipts.
  No migration, dependency, provider call or automatic financial aggregation.


## 0.23.0 — Correct individual photo attachments

- Remove a photo from one asset gallery while preserving its private original, other gallery attachments, transcriptions and claim evidence. Reattach by uploading the same file to that item.
- Add owner-scoped HTTP/MCP correction and gallery action, audited with both photo and asset IDs. Safe retries do not repeat removal; stale actions cannot remove a newly reattached link. No migration or dependency change.

## 0.22.0 — Explicit receipt currencies

- Support printed USD, EUR, GBP, CAD, AUD and JPY line totals in suggestions, review and immutable history. Store exact integer minor units; use whole yen for JPY and two decimals for the others. Never convert currencies or infer them from symbols.
- Migration `0016_receipt_currencies` preserves existing USD history and request replay. Downgrade refuses to discard non-USD claims. Existing API callers default to USD for compatibility.

## 0.21.0 — Source-backed purchase-detail suggestions

- Find uniquely labeled USD line totals and ISO purchase dates in saved receipt sources without an AI request. Copy exact passages into an editable draft only on request; saving still uses owner-scoped validation and immutable revision history.
- Ambiguous, invalid, unsupported or unavailable source values remain unknown. No accounting arithmetic, automatic inventory changes, schema migration or new dependency.
- Add a linked source-version badge at the top of the README and a version consistency test. The badge does not describe an already running container.

## 0.20.0 — Source-backed receipt purchase details

- Add explicit USD line totals and purchase dates to confirmed purchased receipt
  lines without another AI request. Require exact item/total and labeled date
  passages; leave ambiguous values unknown. Store line totals as integer cents,
  once for all units; never infer a unit price or multiply by quantity.
- Keep immutable revisions with source quotes, purchase-world date and recorded
  time. Correct or withdraw claims without erasing history; guard concurrent edits
  and preserve exact retries after a lost response. Source corrections/deleted
  originals block new writes while historical claims remain readable.
- Add private HTTP/MCP reads and writes, paginated history and a receipt editor.
  Migration `0015_receipt_details` adds a constrained typed claim table; no new
  dependency. No automatic financial extraction, accounting totals or redeployment.

## 0.19.0 — Review multiple receipt items and quantities

- Suggest up to eight source-quoted receipt lines from a saved note, reviewed PDF
  text or photo transcription; explicitly select ownership, quantities and new or
  existing physical units before one atomic confirmation. Cap each receipt at 20 units.
- Preserve drafts in Review, exact source provenance and reviewed field values;
  block stale sources, deleted originals, duplicate unit choices and changed matches.
  Retry a lost confirmation safely without duplicate records or partial batches.
- Share the existing consent-gated OpenAI/Claude/Gemini runtime, owner-scoped HTTP
  and MCP services. Migration `0014_receipt_proposals` adds private draft/replay
  storage; no new dependency. Prices, dates and accounting remain deferred.

## 0.18.0 — Browse and capture private memories

- Replace the Memories placeholder with an owner-scoped evidence library: literal
  search, source-type filters, current/earlier note versions and stable newest-first
  pagination. Original source reads, corrections and history reuse shared services.
- Capture exact note text directly without a chat, AI permission or inferred assets;
  preserve request identity through connection loss and repeated/concurrent capture.
- Preserve photo/PDF categories through corrections; expose private library reads
  through typed MCP. No schema migration, provider call or new dependency.
- Fix asset evidence views that discarded photo/PDF provenance and mislabeled
  derived text as an original statement. Use the shared evidence panel, including
  original-file deletion notices and correction history.
- Fix evidence image overflow caused by a heading layout rule affecting all child
  sections; ignore stale source/page responses during navigation and search.


## 0.17.0 — Private PDF evidence and reviewed text

- Upload owner-scoped PDF originals, inspect automatic text extraction and explicitly
  save reviewed text to searchable memory. No automatic asset creation or provider call.
- Preserve original downloads and source links through note corrections and graph
  evidence inspection. Original deletion retains reviewed source history explicitly.
- Bound uploads to 8 MiB / 10 pages, extraction to 4,000 characters, and private PDF
  storage to 200 active files / 256 MiB per user. Use a separate local parser process
  with decompression/time limits and Linux CPU/address-space limits. No inline PDF
  execution or OCR. Migration `0013_private_documents`; add pinned pypdf dependency.

## 0.16.0 — Google Gemini alongside OpenAI and Claude

- Add Google Gemini to private Chat, saved choices and photo reading using an
  owned `google` AI credential. Google sign-in OAuth remains separate.
- Use stateless Gemini Interactions requests with structured output, streaming,
  optional sanitized JPEG input, fixed endpoint and header-only API key. Disable
  provider storage/background work/tools and retain shared consent/usage checks.
- Do not expose thought content. Validate final structure, citations and usage;
  redact failures and reject managed-agent model IDs. Google currently documents
  Antigravity agent without the structured-output/output-token controls required
  by this runtime; its integration remains deferred. No schema or SDK dependency
  change. Live Google access remains unverified (synthetic/mocked tests only).

## 0.15.0 — Recall sourced records and graph connections

- Let the shared chat runtime plan up to two exact record-name lookups, inspect
  current sourced facts and optionally read a bounded one-step neighborhood.
  Same-named physical items remain separate and ambiguous matches stay explicit.
- Preserve source corrections, assertion status, valid dates and original citations.
  Cap records, facts, sources and total context; omit whole facts rather than
  truncating their values. Add graph links for inspected records in replies.
- Expose owner-scoped exact name/alias lookup through private MCP. The app runtime
  uses the same domain services with no model writes, SQL access or extra provider
  planning call. No migration; live-provider access remains unverified.

## 0.14.0 — Streaming evidence-backed replies

- Stream OpenAI and Claude answer text into a marked, transient draft in Chat.
  Validate the completed structure and source citations before saving the reply.
- Drop drafts on failure, cancellation or disconnect; preserve the saved request
  and existing idempotent retry behavior. Bound provider events, output, queue size
  and browser stream parsing; cancel pending work when the stream closes.
- Keep per-call consent, credential/session checks, usage limits and fixed endpoints.
  No schema change. Provider streaming is verified with synthetic mocked events;
  configured live-provider access remains unverified.

## 0.13.0 — Remember private chat model choices

- Explicitly remember or forget an owned AI connection and model from Chat; restore
  that account's choice when reopening Chat. No browser storage or shared defaults.
- Saving a choice never enables external AI, reads a secret or calls a provider.
  Removed credentials clear the effective choice without a provider fallback.
- Migration `0012_chat_preferences` adds an owner-scoped preference table and leaves
  existing conversations, memory, appearance and external-AI consent intact.

## 0.12.0 — Sourced home and vehicle profiles

- Add specifications, VIN/serial/model, filter dimensions, room paint and maintenance
  statements to existing private asset/place records, or explicitly create a distinct
  home/vehicle record. Creating a profile does not assert ownership or parts fitment.
- Preserve exact source statements, stated/inferred/unknown status, optional world-valid
  dates and correction history. Retry-safe atomic writes reuse the memory core.
- Add private profile inspection to MCP, a responsive Profiles view, original evidence
  inspection and graph navigation. No migration or external lookup is required.

## 0.11.0 — Interactive evidence-backed graph

- Explore private records and their stored connections with keyboard-accessible nodes,
  zoom, bounded one/two-step traversal and an alternative record list.
- Inspect fact status, direction, valid dates and original evidence; inferred and unknown
  relationships have distinct line styles. Literal facts remain visible without edges.
- Navigate between graph records and asset details/photos. All graph reads reuse the
  owner-scoped memory service; no model calls, invented connections or schema change.

## 0.10.0 — Per-user light and dark themes

- Select Light, Dark or System in Settings; preserve the choice per user across
  sessions without changing external-AI consent or credential storage.
- Apply semantic cream/sage and dark forest palettes across existing views,
  including chat, assets, photos, review/evidence controls and status banners.
- Migration `0011_appearance` defaults existing preferences to System. Sign-out
  and account changes clear the previous account's appearance; System follows
  device changes without storing private preferences in browser storage.

## 0.9.0 — Claude alongside OpenAI

- Select a private Claude (`anthropic`) or OpenAI connection for evidence-backed
  answers, saved-note proposals and photo reading, with one shared memory store.
- Route by owned credential metadata to fixed provider endpoints; no fallback,
  arbitrary URLs or model write tools. Both providers share consent, daily budget,
  per-call credential checks, cancellation, citation and source validation.
- Add bounded Claude Messages JSON/vision adapter with local strict validation,
  supported wire schema normalization, redacted failures and no retries.
- New live-call result records retain provider/model labels. Switching a connection
  clears the model field. No migration or new runtime dependency; live provider
  access remains unverified (synthetic/mocked verification only).


## 0.8.0 — Persistent review queue

- Add a private paginated Review inbox for pending item proposals and unresolved
  identity matches, with filters, exact evidence and shared Chat review state.
- Resolve same/different items or exclude a discovery with stale-head/candidate
  checks and safe replay. Not sure leaves the record pending; multi-unit linking
  requires a distinct existing item for every unit. Names never auto-merge items.
- Typed authenticated HTTP/MCP adapters reuse existing durable proposal/decision
  records; no migration or model calls are required by this feature.


## 0.7.0 — Private receipt and nameplate photos

- Add authenticated JPEG/PNG/WebP upload, private originals, metadata-free previews,
  per-user byte deduplication, paginated Photos and asset galleries, and downloads.
- Explicit consented vision reading produces an unverified, correctable transcription
  and one reviewed item proposal; attaching a photo never creates assets. Accepted
  proposals link the original photo atomically to their resulting items.
- Enforce 8 MiB / 20 MP / single-frame inputs, two concurrent uploads, 200 photos /
  256 MiB per owner, and existing AI budgets/session/cancellation rules.
- Migration `0010_private_photos` stores deferred binary originals and previews in
  the private SQLite database so operator snapshots restore both bytes and links.
  Deletion clears originals/previews; derived text/history and earlier backups remain.
- Pillow 13.0.0 is pinned; model wire and privacy checks use synthetic providers only.


## 0.6.0 — 2026-10-18

- Add sourced ownership updates (owned, sold, returned, no longer owned),
  single-item confirmation undo and explicit evidence reassociation.
- Keep correction explanations, original evidence, prior decisions and dated
  ownership intervals; reject stale/concurrent conflicting actions.
- Migration 0009 adds private action history without rewriting existing data.

## 0.5.0 — 2026-10-18

- Browse/search private inventory and include historical asset records.
- Inspect sourced item details, inferred ownership, decision/fact history and
  exact original evidence with bounded paging. No schema or data migration.

## 0.4.0 — 2026-10-18

- Propose one physical item from a selected saved note using bounded OpenAI
  extraction; no inventory changes occur until explicit human review.
- Review/edit exact evidence and supported identifiers, check private duplicate
  candidates, and explicitly choose the same or a different physical item.
- Preserve original proposals, human-reviewed fields and source evidence. Reject
  without creating inventory; retry confirmation safely after lost responses.
- Migration `0008_asset_proposals` adds owner-constrained proposal history without
  rewriting existing notes, accounts, sessions, chats, settings or inventory.
- Block stale-note confirmation and duplicate manufacturer-scoped serial creation;
  keep ownership inferred and missing prices/dates unknown. One item per note;
  broader extraction, accepted-asset correction UI and uploads remain later.

## 0.3.0 — 2026-10-18

- Add explicitly enabled, one-click test login with a shared test workspace and
  persistent warning banner. Normal sign-in remains protected and separate.
- Display the application version on the login screen and inside the app, with
  the exact Git revision when embedded by the release process.
- Establish one application version source and verify package/API/container
  metadata agree. Older images retain their original metadata.

This is the initial visible versioning baseline. Source completion does not imply
that the corresponding Docker image has been published or deployed.
