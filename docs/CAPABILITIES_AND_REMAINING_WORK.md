# What LifeGather can do and what remains

Reviewed 2026-10-20 against fetched `origin/main` at
`2b46d3939dcd26e5a609d2a8c04000247811b108`, application **0.55.1**, migration **0024**.
This is a source-capability inventory, not a check of an installed server, live
credentials or published image. Release counts and branch names are not capability
scores. Historical documents sometimes say later features are missing; the latest
release ledger and feature documents take precedence.

## Available workflows

These 12 categories are a human-readable grouping, not a percentage of completion.
They are implemented with recorded synthetic test coverage; this documentation
update did not rerun the application suites or exercise live providers/mailboxes.

| Workflow | What you can do now | Practical boundary |
| --- | --- | --- |
| Private accounts | Use Google or configured verified email/password login; maintain private records, credentials and jobs per user. | SMTP delivery needs configuration/live verification; no shared spaces. |
| Personal memory | Save notes, search them, inspect sources, correct statements and retain earlier history. | No guarantee of semantic recall for every paraphrase. |
| Inventory | Add possessions manually or through reviewed discovery, browse them and correct ownership/identity. | A name match never proves two physical items are the same; inferred ownership is labelled. |
| Evidence library | Upload private photos/PDFs, review extracted text and link/reuse photos on assets. | Gallery attachment alone does not prove a claim; parsing and extraction are bounded. |
| Receipt processing | Review multiple receipt items and quantities; keep separate physical units; save sourced money/date claims. | Six explicit currencies: USD, EUR, GBP, CAD, AUD, JPY. Money/date review is not automatic accounting. |
| Purchase reconciliation | Associate order, receipt, shipment and payment evidence with the same purchase; correct and reverse supported decisions. | No payment allocation/refund ledger; shipment evidence alone is not proof of delivery. |
| Duplicate correction | Compare records, explicitly consolidate two eligible assets and reverse when safe. | No bulk/chained consolidation; conflicting identities and sibling units are guarded. |
| Profiles and graph | Save sourced home/vehicle specifications and named custom details; browse evidence-backed relationships. | No automatic VIN/parts compatibility guarantee. |
| Contextual assistant | Keep chat docked/resizable at any edge; use explicit commands to navigate or save supported supplied profile fields. | Navigation sidebar itself is not yet dockable; broader AI writing is absent. |
| AI questions | Use OpenAI, Claude or Gemini for streaming bounded sourced answers and supported image/receipt reading. | Three provider adapters, not free bundled AI; configured consent, credentials and budgets apply; live access is not established by mock tests. |
| Gmail discovery | Connect Gmail separately, request bounded text imports or AI purchase discovery, and configure daily/weekly scans with progress/cancel/recovery. | One implemented email provider; no arrival trigger, attachments or inferred financial values. Chat starts text-evidence scans; purchase-discovery mode is selected in Scans/schedules. |
| Maintenance and portability | Track stated dated/undated tasks, complete/cancel/reopen with history; download private JSON or ZIP originals; operator can make encrypted full-installation backups and restore to a new directory. | No automatic maintenance reminders/recurrence. Personal archives have no user import/restore; operator recovery is a separate CLI workflow. |

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

| Area | Remaining scope | What is already delivered |
| --- | --- | --- |
| Power Center | Primary page, capability/readiness scoring, freshness, automatic actionable health checks and newly unlocked capability explanations. | Connection/settings and scan primitives only; see the [new design](superpowers/specs/2026-10-20-power-center-design.md). |
| Navigation docking | Left default, four-edge docking, resizing, remembered per-account layout, accessible controls and assistant coexistence. | Assistant docking/resizing already exists, right default. |
| Assistant breadth | Broader supported conversational edits/planning, conversational AI purchase-discovery initiation and arbitrary supported image questions; explicit permission boundaries. | Streaming recall, deterministic supplied-field edits, photo upload/reading and Chat text-evidence scan requests. |
| Extraction | Automatic evidence-validated price/date extraction and broader financial/document extraction; email attachments. | Reviewed PDFs/multi-item receipts, explicit sourced money/date claims, inline-email item discovery. |
| Broader documents | Add Word `.docx`, Excel `.xlsx`, text `.txt`, Markdown `.md` and CSV `.csv` uploads, bounded local extraction, review/search and original-file provenance. See the [document support design](superpowers/specs/2026-10-20-broader-document-support-design.md). | Documents currently accepts PDF; photos have their separate existing workflow. |
| Reconciliation | Larger/bulk/chained consolidation where justified, fuller shipment/unit workflows and financial allocation, split/combined payments, refunds/returns accounting. | Two-record reversible consolidation, replacement links and reversible evidence moves/grouping. |
| Photo experience | Saved-photo attachment picking in Chat, event galleries and remaining direct photo/graph navigation workflows. | Chat upload/saved-photo reading, asset galleries, existing photo reuse/removal and receipt-photo review. |
| Web research | Explicitly requested, dated cited research with external-data permissions and identity uncertainty. | Local sourced recall is separate. |
| Banking and finances | Statement import, then live bank/card sync, exact-money accounting and purchase reconciliation. | Evidence grouping and reviewed purchase claims, not bank connectivity. |
| Portability and privacy | User-facing archive import/restore, broader selective deletion/erasure and retention UX, convenient backup/recovery management where justified. | JSON/ZIP export, reviewed transcript deletion, existing file controls and encrypted operator recovery. |
| Auth and account controls | Session/device management UI, native-account Google linking, verified login-email changes and stronger local breach-password checks. | Google and verified password flows, reset/setup and session revocation. |
| Credentials | Credential rotation tooling and health/reconnection workflows with safe vault handling. | Encrypted private vault and installation recovery including its key. |
| Maintenance automation | Explicit recurrence, supported interval/mileage rules, reminders and notifications. | Manual sourced tasks/dates/states/history/current recall. |
| Warranties and insurance | Sourced coverage, expiry, claim packets and insurance inventory exports. | Generic evidence/profile storage only. |
| Recalls and consumables | Verified product recall checks, consumable tracking and relevant reminders. | Generic inventory/specifications only. |
| Subscriptions | Recurring-payment discovery, subscription records, renewals and user controls. | Not unlocked merely by Gmail or saved financial credentials. |
| Timelines and dashboards | Useful cross-domain timelines, real-data overview/insights and financial summaries after their source domains exist. | Record/history views and graph; screenshot totals are not real metrics. |
| More sources | Outlook/iCloud, calendar/contacts/photos, cloud files, watched local folders/document scanners, retailer exports and home devices; investment/vehicle/insurance services require separate scoping. | Gmail plus manual local uploads and three AI provider adapters. Screenshot logos do not mean support. |
| Additional AI runtimes | Revisit managed Antigravity only if its official contract can meet bounded output/usage needs; evaluate other providers/local extraction separately. | OpenAI, Claude, Gemini; Antigravity is deferred for documented API limitations. |
| Asset customization | Reusable asset templates and broader correction/undo coverage where supported safely. | Named sourced profile fields, field history and specific reversible decisions. |

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
