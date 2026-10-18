# Changelog

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
