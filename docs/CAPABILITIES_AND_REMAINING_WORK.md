# What LifeGather can do and what remains

**Active priorities, 2026-10-21:** [tracking-first feature plan](FEATURE_PLAN.md).
The user chose reliable AI-assisted tracking before proactive automation, plus a
dedicated UI beautification phase. The remaining-scope table is a capability-gap
inventory, not a mandatory implementation queue. The active plan classifies every
area as core, conditional or deferred; no implemented feature is removed.

Current source baseline for this priority revision: v0.59.0, migration 0026,
fetched main `41cd377631a9996b1cda901a98d61071c7d06628`. The older audit below
records historical verification; no application test suite was rerun for this
documentation-only change.

Reviewed 2026-10-20 against fetched `origin/main` at
`2b46d3939dcd26e5a609d2a8c04000247811b108`, application **0.55.1**, migration **0024**.
This is a source-capability inventory, not a check of an installed server, live
credentials or published image. Release counts and branch names are not capability
scores. Historical documents sometimes say later features are missing; the latest
release ledger and feature documents take precedence.

Subsequent source updates: v0.56.0 adds broader documents and migration 0025;
v0.57.0 adds dockable/resizable navigation; v0.58.0 adds Power Center local
readiness and observed health without another migration. The
baseline above identifies the original audit, with delivered changes noted below.

## Available workflows

These 12 categories are a human-readable grouping, not a percentage of completion.
They are implemented with recorded synthetic test coverage; this documentation
update did not rerun the application suites or exercise live providers/mailboxes.

| Workflow | What you can do now | Practical boundary |
| --- | --- | --- |
| Private accounts | Use Google or configured verified email/password login; maintain private records, credentials and jobs per user. | SMTP delivery needs configuration/live verification; no shared spaces. |
| Personal memory | Save notes, search them, inspect sources, correct statements and retain earlier history. | No guarantee of semantic recall for every paraphrase. |
| Inventory | Add possessions manually or through reviewed discovery, browse them and correct ownership/identity. | A name match never proves two physical items are the same; inferred ownership is labelled. |
| Evidence library | Upload private photos plus PDF, DOCX, XLSX, TXT, Markdown and CSV documents; review searchable text, select tabular previews and link/reuse photos on assets. | v0.56.0 adds documents; no macros/formula execution, OCR, legacy Office or guaranteed layout preservation. |
| Receipt processing | Review multiple receipt items and quantities; keep separate physical units; save sourced money/date claims, with v0.70.0 AI suggestions grounded in exact printed passages and flagged ambiguities. | Six explicit currencies: USD, EUR, GBP, CAD, AUD, JPY. Money/date review is not automatic accounting. |
| Purchase reconciliation | Associate order, receipt, shipment and payment evidence with the same purchase; correct and reverse supported decisions. | No payment allocation/refund ledger; shipment evidence alone is not proof of delivery. |
| Duplicate correction | Compare records, explicitly consolidate two eligible assets and reverse when safe. | No bulk/chained consolidation; conflicting identities and sibling units are guarded. |
| Profiles and graph | Save sourced home/vehicle specifications and named custom details; browse evidence-backed relationships. | No automatic VIN/parts compatibility guarantee. |
| Contextual assistant | Keep chat docked/resizable at any edge; use explicit commands to navigate or save supported supplied profile fields. Primary navigation also docks/resizes independently in v0.57.0. | Navigation defaults left; assistant defaults right. Broader AI writing is absent. |
| AI questions | Use OpenAI, Claude or Gemini for streaming bounded sourced answers and supported image/receipt reading. | Three provider adapters, not free bundled AI; configured consent, credentials and budgets apply; live access is not established by mock tests. |
| Gmail discovery | Connect Gmail separately, request bounded text imports or AI purchase discovery, and configure daily/weekly scans with progress/cancel/recovery. | One implemented email provider; no arrival trigger, attachments or inferred financial values. Chat starts text-evidence scans; purchase-discovery mode is selected in Scans/schedules. |
| Maintenance and portability | Track stated dated/undated tasks, complete/cancel/reopen with history; download private JSON or ZIP originals and restore that ZIP into an empty account; operator can make encrypted full-installation backups and restore to a new directory. | No automatic maintenance reminders/recurrence. Archive restore needs an empty account and refuses records already in the installation (no merging or ID rewriting); operator recovery is a separate CLI workflow. |

### Everyday example

Record a mower, attach its receipt/nameplate, review its model and purchased units,
save a sourced filter specification, and create a maintenance task with a stated
due date. Later ask for the filter specification and follow its source. Correct a
mistake without erasing its earlier statement. A requested/scheduled Gmail discovery
run can find sufficiently identified receipt items, while uncertain matches wait
for review. It cannot yet order a filter, infer a reliable service interval, send
an automatic reminder or guarantee every receipt was found.

## Remaining product work

This consolidates documented unfinished scope; it is not authorization to implement
all items together or a promise that each expansion is required for a useful release.
Review current source, dependencies and acceptance criteria before each increment.

| Area (priority is defined in the active feature plan) | Remaining scope | What is already delivered |
| --- | --- | --- |
| Power Center | Live remote/provider-model probing and richer connection diagnostics require later scope. | v0.58.0 adds the primary page, versioned readiness, observed health/freshness, automatic local checks and connection changes; see [Power Center](POWER_CENTER.md). |
| Assistant breadth | Broader supported conversational edits/planning and arbitrary supported image questions; explicit permission boundaries. | v0.60.0 [AI asset assistant](AI_ASSISTANT.md) for model-selected asset search, creation and atomic multi-field updates (asset types and typed template fields since v0.63.0); v0.62.0 assistant-started Gmail discovery/evidence scans; streaming recall, deterministic supplied-field edits, photo upload/reading and Chat text-evidence scan requests. |
| Extraction | Broader financial/document extraction (taxes, totals, allocation); email attachments. | Reviewed PDFs/multi-item receipts, explicit sourced money/date claims, v0.70.0 AI price/currency/date suggestions checked against printed passages, inline-email item discovery. |
| Broader documents | Additional formats, richer layout/OCR and broader document extraction require separately scoped increments. | v0.56.0 adds DOCX, XLSX, TXT, Markdown and CSV alongside PDF with bounded local review, source locations and original preservation; see [Documents](DOCUMENTS.md). |
| Reconciliation | Larger/bulk/chained consolidation where justified, fuller shipment/unit workflows and financial allocation, split/combined payments, refunds/returns accounting. | Two-record reversible consolidation, replacement links and reversible evidence moves/grouping. |
| Photo experience | Saved-photo attachment picking in Chat, event galleries and remaining direct photo/graph navigation workflows. | Chat upload/saved-photo reading, asset galleries, existing photo reuse/removal and receipt-photo review. |
| Web research | Gemini research, saving reviewed research findings as evidence, and fetching/reading full manuals. | v0.67.0 [web research](WEB_RESEARCH.md): on request, OpenAI/Claude web search with dated citations; saved record details sent only when shared per request. |
| Banking and finances | Statement import, then live bank/card sync, exact-money accounting and purchase reconciliation. | Evidence grouping and reviewed purchase claims, not bank connectivity. |
| Portability and privacy | Merging an archive into an account that already has records, erasure of memories/sources and retention beyond chat conversations, convenient backup/recovery management where justified. | JSON/ZIP export, archive restore into an empty account, reviewed transcript deletion, file controls with [multi-select deletion and conversation retention](SELECTIVE_DELETION.md) (v0.76.0) and encrypted operator recovery. |
| Auth and account controls | Session/device management UI, native-account Google linking, verified login-email changes and stronger local breach-password checks. | Google and verified password flows, reset/setup and session revocation. |
| Credentials | Credential rotation tooling and health/reconnection workflows with safe vault handling. | Encrypted private vault and installation recovery including its key. |
| Maintenance automation | Explicit recurrence, supported interval/mileage rules, reminders and notifications. | Manual sourced tasks/dates/states/history/current recall. |
| Warranties and insurance | Sourced coverage, expiry, claim packets and insurance inventory exports. | Generic evidence/profile storage only. |
| Recalls and consumables | Verified product recall checks, consumable tracking and relevant reminders. | Generic inventory/specifications only. |
| Subscriptions | Recurring-payment discovery, subscription records, renewals and user controls. | Not unlocked merely by Gmail or saved financial credentials. |
| Timelines and dashboards | Useful cross-domain timelines, real-data overview/insights and financial summaries after their source domains exist. | Record/history views and graph; screenshot totals are not real metrics. |
| More sources | Outlook/iCloud, calendar/contacts/photos, cloud files, watched local folders/document scanners, retailer exports and home devices; investment/vehicle/insurance services require separate scoping. | Gmail plus manual local uploads and three AI provider adapters. Screenshot logos do not mean support. |
| Additional AI runtimes | Revisit managed Antigravity only if its official contract can meet bounded output/usage needs; evaluate other providers/local extraction separately. | OpenAI, Claude, Gemini; Antigravity is deferred for documented API limitations. |
| Asset customization | Richer typed widgets, required-field migrations and broader correction/undo where supported safely. | v0.59.0 adds [editable starter/custom types](ASSET_TYPES.md), selection in manual entry, safe later field additions, definition history and authenticated MCP view/add/edit; existing named sourced details remain supported. |
| UI beautification | Dedicated visual/usability refinement after the tracking reliability gate: typography, spacing, consistent states, responsive/docked layouts, accessibility and Light/Dark screens. | Existing theme choices, semantic components and dockable panels provide the foundation; this phase is planned, not delivered. |

## Operational verification and deferred decisions

- Verify configured SMTP delivery and password-reset mail end to end. Provider
  adapters/Gmail were tested synthetically; actual provider/model access, Gmail
  consent and refresh-token longevity still need installation-specific verification.
- Confirm the running installation's version/revision separately from source.
  Updating this checkout does not update TrueNAS, restart an app or prove image publication.
- Dedicated mobile/camera app, offline/PWA/share-menu and remote/domain/tunnel setup
  remain explicitly deferred. Responsive web and ordinary uploads already exist.
- Brand/domain/trademark clearance remains unresolved. Shared spaces, public SaaS,
  vector databases and infrastructure expansion remain anti-goals unless separately requested.

## Evidence and maintenance

Reconciled from [project plan](../PROJECT_PLAN.md), [release changelog](../CHANGELOG.md)
and [ordered ledger](superpowers/plans/2026-10-18-ordered-roadmap.md), with current
feature docs for [assistant](CONTEXTUAL_ASSISTANT.md), [discovery](EMAIL_DISCOVERY.md),
[scans](EMAIL_SCANS.md), [receipts](MULTI_ITEM_RECEIPTS.md), [photos](PHOTO_EVIDENCE.md),
[consolidation](ASSET_CONSOLIDATION.md), [maintenance](MAINTENANCE.md),
[archives](PERSONAL_ARCHIVE.md), [recovery](OPERATOR_RECOVERY.md) and
[account limitations](EMAIL_PASSWORD_AUTH.md). Checked the current App navigation
directly. Update this inventory as bounded releases actually land; do not treat
older stage-specific exclusions as proof a subsequently released feature is absent.
