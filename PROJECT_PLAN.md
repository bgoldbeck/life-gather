# LifeGather — Product and Engineering Plan

**Status:** v0.85.0 adds reconnect prompts for expired Gmail and AI sign-ins; tracking and evidence-backed recall remain the active priorities.
**Date:** Updated 2026-10-23

v0.85.0 remembers when Google or an AI provider refuses a saved sign-in and offers
one-click Reconnect in Power Center, Scans, chat and Settings. Migration 0036. See
[reconnect plan](docs/superpowers/plans/2026-10-23-reconnect-prompts.md).

v0.84.1 hardens saved web research retries with durable owner-scoped receipts,
removed-result acknowledgments and records format 6. Migration 0035; formats 4/5
remain restorable. See [retry plan](docs/superpowers/plans/2026-10-22-research-save-receipts.md).

**Active priorities:** [tracking-first feature plan](docs/FEATURE_PLAN.md).
User decision, 2026-10-21: make tracking and evidence-backed recall dependable
before adding proactive automation, then complete a dedicated UI beautification
phase. Natural-language AI tool use comes first; coherent multi-field changes
must not require one turn per field. Existing requested/scheduled scans stay
available. This plan supersedes historical future-feature ordering below; deferred
domains are candidates, not a commitment to implement every feature.

Current capability inventory and consolidated outstanding scope:
[what LifeGather can do and what remains](docs/CAPABILITIES_AND_REMAINING_WORK.md).
User design additions, 2026-10-20: [Power Center and dockable navigation](docs/superpowers/specs/2026-10-20-power-center-design.md).
[Power Center](docs/POWER_CENTER.md) local readiness/observed health is delivered
in v0.58.0; [navigation docking](docs/NAVIGATION.md) is delivered in v0.57.0,
independently of the existing right-default contextual assistant.

Planned user addition, 2026-10-20: [editable asset types](docs/superpowers/specs/2026-10-20-custom-asset-types-design.md)
provides Vehicle, Appliance, Electronics, Furniture and Tools & Equipment as editable
defaults, private custom types selectable during manual entry, and safe later field
additions preserving existing evidence/history. Delivered in v0.59.0 with migration
0026, records format 4 and authenticated MCP view/add/edit. See [Asset types](docs/ASSET_TYPES.md).

User addition, 2026-10-20: [broader document support](docs/superpowers/specs/2026-10-20-broader-document-support-design.md)
targets Word (`.docx`), Excel (`.xlsx`), plain text, Markdown and CSV alongside PDF,
with private originals, bounded local extraction, reviewed searchable text and
source locations. Implemented in v0.56.0 with selectable previews, review/search,
format-aware originals and archive/recovery coverage. See [Documents](docs/DOCUMENTS.md).

Current correction: v0.58.1 prevents stale UI/version confusion after deployment:
startup pages revalidate, loaded UI build labels stay pinned and session checks
offer an explicit Reload when the server build changes. Drafts are not discarded
automatically. No migration/dependency; see [Versioning](docs/VERSIONING.md).

v0.58.0 adds private Power Center readiness, source filters,
observed health/freshness, recovery links and connection capability explanations.
Local checks never probe providers or start ingestion; live model/grant health
without processing evidence remains unknown. No migration or dependency.

v0.57.0 adds four-edge dockable/resizable primary navigation,
left default, per-account browser preferences, pointer/keyboard controls, reset
and compact fallback while retaining page/chat drafts. No migration or new dependency.

v0.56.0 adds broader private document evidence and format-aware
original/archive/recovery handling with migration 0025. Reviewable local extraction
supports DOCX/XLSX/TXT/Markdown/CSV alongside PDF; no AI, macros or formula execution.

v0.55.1 corrects maintenance evidence recall: older matching
statements link to the current typed revision, and source inspection labels
historical task statements. No schema or provider permission change.
v0.55.0 adds [sourced maintenance tasks](docs/MAINTENANCE.md).
Explicit manual plans, optional calendar dates/timezones, completion/cancellation
and preserved revisions are available in Profiles and the global Maintenance view.
Fresh versions and stable retries protect changes; original record links survive
identity consolidation. Migration 0024 adds typed task/history tables; personal
records format 3 includes their history. No automatic intervals, reminders or AI calls.

v0.54.0 adds [reviewed conversation deletion](docs/CONVERSATION_PRIVACY.md).
Fresh owner-scoped previews, separate pending-request stopping and explicit
confirmation remove one transcript while retaining independently saved records.
Minimal deletion receipts permit safe retries; late completions cannot restore
canceled or deleted requests. No migration, dependency or model deletion tool.

v0.53.0 lets the [contextual assistant](docs/CONTEXTUAL_ASSISTANT.md)
save supplied named custom details with original evidence and correction history.
Pinned context, reserved identity fields, conflicts and exact retries remain guarded;
consolidated-member correction retries preserve original subjects. No migration,
dependency, AI tool or provider request.

v0.52.0 adds a [personal records and originals ZIP](docs/PERSONAL_ARCHIVE.md)
from one owner-scoped PostgreSQL snapshot, with exact original bytes and a hash
manifest. Existing JSON downloads remain available. No schema, dependency or
automatic import/restore; all-user encrypted operator recovery remains separate.

v0.51.0 adds [named custom sourced profile details](docs/CUSTOM_PROFILE_DETAILS.md).
Create and correct descriptive fields through the existing private fact/history
services, with readable labels, original evidence, unknowns and dates. Reserved
identity fields retain their meaning. No schema, dependency or AI-tool change.

v0.50.0 adds [encrypted operator recovery](docs/OPERATOR_RECOVERY.md):
consistent whole-installation backup, authenticated verification and restore into
a new directory, including original files, configuration and the separate vault
key. No automatic activation, HTTP/MCP recovery endpoint, dependency or migration.
v0.50.1 lets verify/restore proceed when old operational settings are incomplete;
configured data/static privacy guards and actual backup configuration remain enforced.

v0.49.0 defaults the [contextual assistant](docs/CONTEXTUAL_ASSISTANT.md)
to the right and adds pointer/keyboard resizing with account-scoped dimensions.
Saved positions and the narrow-screen bottom layout remain supported; no migration.

v0.48.0 adds [reversible two-record asset consolidation](docs/ASSET_CONSOLIDATION.md).
An explicit fresh preview and human identity choice produce one current item while
preserving original records, evidence, conflicting statements and temporal history.
Shared browsing/recall/matching and guarded reversal use migration 0023. Portability
format 2 includes consolidation history; bulk/chain consolidation remains ahead.

v0.47.0 adds [private record downloads](docs/RECORD_EXPORT.md)
from a consistent owner-scoped snapshot with history, quantities and exact money.
Original-file exports and user-facing import/restore remain ahead.

v0.46.0 adds explicit manual inventory entry directly on
Assets, sharing physical identity matching, provenance, stated ownership and
correction history with existing discovery. No new schema or AI call is required.
The same deliberately bundled release adds a persistent docked assistant,
selected-record context, explicit chat navigation and sourced profile edits;
see [contextual assistant](docs/CONTEXTUAL_ASSISTANT.md). Broader AI write planning
and external browser-control bridges remain ahead.
v0.45.0 adds shared server-owned audit origins and private
field history in Profiles, Assets and Graph. Preserve unknown legacy attribution,
explicit correction links, evidence, confidence and both time dimensions.
See [change history](docs/CHANGE_HISTORY.md). Custom asset templates remain ahead.
v0.43.0 adds explicit bounded Gmail text-evidence scans from
Chat, with atomic queue/result saving and existing Scans progress/cancellation.
Conversational AI purchase discovery and free-form agent planning remain ahead.
v0.42.0 adds explicit multi-item receipt-photo reading in Chat,
with unverified transcription, quantities and the existing human receipt review.
v0.41.0 adds explicit private photo uploads directly in Chat,
then a separate AI reading using the existing single-item review flow.
v0.40.0 adds explicit saved-photo reading in the current Chat,
using the existing private original, configured provider and single-item review.
Arbitrary photo questions and automatic photo financial extraction remain ahead.
v0.39.0 adds [complete bounded current-record comparison](docs/RECORD_COMPARISON.md)
before duplicate corrections, preserving conflicts, quantities and provenance.
The read-only comparison makes no identity decision; v0.48.0 adds a separate
explicit two-record consolidation and guarded reversal workflow.
v0.38.0 adds [requested/scheduled Gmail purchase discovery](docs/EMAIL_DISCOVERY.md)
using private configured AI adapters, exact evidence validation, inferred inventory,
existing identity review/corrections and durable extraction reuse. Attachment and
financial extraction and conversational purchase-discovery scans remain ahead. The milestone
paragraphs below include historical descriptions of earlier increments.

Historical continuation, 2026-10-18: [implementation ledger](docs/superpowers/plans/2026-10-18-ordered-roadmap.md).
Use the [active feature plan](docs/FEATURE_PLAN.md) for new work priorities.
Per-user Light/Dark/System appearance is implemented in v0.10.0; the interactive
graph is implemented in v0.11.0; sourced home/vehicle profiles are implemented in v0.12.0. Private saved chat choices are implemented in v0.13.0; streaming replies are implemented in v0.14.0; bounded sourced record/connection recall is implemented in v0.15.0. Google Gemini support is implemented in v0.16.0; managed Antigravity is deferred for documented API limitations. Private reviewed PDF evidence is implemented in v0.17.0; [multi-item receipt review and sourced quantities](docs/MULTI_ITEM_RECEIPTS.md) are implemented in v0.19.0. Explicit sourced line totals and purchase dates are implemented in v0.20.0; editable source suggestions in v0.21.0 and USD/EUR/GBP/CAD/AUD/JPY support in v0.22.0 extend that workflow. Broader financial extraction and accounting remain ahead. Current asset-linked purchase browsing is implemented in v0.24.0; bounded reviewed purchase recall is implemented in v0.25.0. Explicitly reviewed clear-item automatic identity decisions are implemented in v0.26.0. Read-only candidate comparison across proposal/receipt/identity review is implemented in v0.27.0. Individual multi-unit evidence reassociation to existing records is implemented in v0.28.0. Atomic clear-identity decisions for explicitly reviewed receipt lines are implemented in v0.29.0. Source/target correction inspection and incoming movement history are implemented in v0.30.0. Reviewed reversible discovery-evidence batches are implemented in v0.31.0; explicit sourced replacement links are implemented in v0.32.0. Existing private photo reuse across item galleries is implemented in v0.33.0. Full-record consolidation remains ahead. Separate private Gmail consent is implemented in v0.34.0 as the prerequisite for [modular requested and scheduled email scans](docs/superpowers/plans/2026-10-18-modular-scheduled-scans.md); requested modular email evidence scans are implemented in v0.35.0; private daily/weekly schedules are implemented in v0.36.0. Reviewed cross-source purchase evidence is implemented in v0.37.0; automatic extraction, financial allocation and conversational scan-start tools remain ahead. Older milestone paragraphs below are historical context.

Source increment: [text memory chat](docs/TEXT_CHAT.md) now provides persistent
private conversations, explicit text capture, keyword recall, source inspection,
saved-note corrections with preserved history,
and optional bounded OpenAI answers. [Saved-note asset proposals](docs/ASSET_PROPOSALS.md)
add a single-item extraction/review increment from stage 5. This is partial stage 4/5
progress; broader extraction, graph corrections/review, and token streaming remain ahead. Asset browsing/corrections, private photo uploads, a persistent review queue and
[OpenAI/Claude adapters](docs/AI_PROVIDERS.md) are now implemented in source.
Live provider access remains unverified; broader ingestion remains ahead. Earlier milestone descriptions
below describe the broader release gates, not additional completed functionality.
**Project name:** LifeGather (working brand; domain and trademark clearance not yet completed)  
**Deployment:** Private, self-hosted Linux server using Docker Compose  
**Development mode:** AI-assisted, using Claude Code and/or Codex with reviewable, test-driven increments

## 1. Product vision

LifeGather is a private, AI-first, persistent personal-memory application. Its job is not merely to store a collection of personal lists. It should gradually accumulate a source-backed understanding of the user's life: possessions, places, organizations, purchases, repairs, events, conversations, expenses, subscriptions, vehicles, warranties, policies, and documents.

The primary control surface is natural-language chat, backed by Model Context Protocol (MCP) tools. The web UI provides search, inspection, corrections, dashboards, timelines, and an early interactive knowledge-graph visualization.

**Primary product principle:** Keep an auditable distinction between (a) what the user or a document asserted, (b) what has been verified, (c) what the AI inferred, and (d) what is unknown.

**Guiding example:** A user says they bought a Husqvarna trimmer. Later they submit a receipt, mention a repair, and ultimately sell it. LifeGather should resolve those references to the same asset, maintain historical ownership and maintenance events, and answer questions with citations back to the underlying messages/receipts. It must not fabricate a price, serial number, exact date, or sale if none is supported.

## 2. Scope: first useful release

The consolidated design is [Personal discovery and recall](docs/superpowers/specs/2026-10-17-personal-discovery-design.md). It records the current user decisions and supersedes earlier single-user and connector-scope assumptions. Review the written design before creating a detailed implementation plan.

First release: Google sign-in → configure a personal AI connection → upload a receipt or nameplate photo → automatically reconcile an item → inspect its evidence and graph connections → recall a useful fact in a later conversation.

Phone-app planning, dedicated camera capture, PWA/share-menu features, and remote-access/domain/tunnel setup are deferred by user decision on 2026-10-17. Basic responsive UI and ordinary image/file uploads remain in scope. Google authentication, private settings, and the deterministic memory-service foundation are implemented in source. The first reconciliation service slice now supports create/enrich/review and reversible evidence reassociation. Email/password signup, verification and recovery now complement Google in source. Chat and authenticated memory adapters follow, then upload and review UI.

- Any Google account can register; every workspace, credential, connector, record, and background job is private to its user. No shared spaces.
- Chat is the primary interface. User update, 2026-10-17: support OpenAI and Claude in the first chat release through one shared runtime and replaceable provider adapters. Keep direct correction, export, and recovery usable without AI.
- Sources, purchases/lines/quantities, product models, physical assets, and reconciliation decisions remain distinct.
- Clear new items are added automatically with inferred ownership; clear matches enrich existing records; ambiguous identities wait in chat and a persistent review queue.
- Early features include receipt/photo uploads, a small interactive graph, evidence views, and simple home/vehicle profiles with sourced specifications.
- Photos are private persistent attachments accessible from each item's Photos & Documents gallery and graph evidence views. Distinguish attaching an image from supporting a specific claim; reuse identical files per user and never create another asset merely by uploading a photo. See [photo evidence design](docs/PHOTO_EVIDENCE.md).
- Preserve provenance, temporal history, idempotency, typed monetary values, tested restore, and two-user isolation from the beginning.

Following the first release: requested email scans, user-defined schedules, requested web research, statement uploads, live bank syncing, additional providers, and separate domain expansions. Email scans start immediately when scope and permissions are clear. Email arrival alone never triggers ingestion. Every live integration requires current API, permission, privacy, and cost review.

Not initial scope: public SaaS infrastructure, shared workspaces, unrestricted AI tools, a vector database, advanced graph layouts, full accounting, native mobile apps, or continuous unsolicited monitoring. Email and bank ingestion are approved roadmap goals, not dependencies of the first release.

The original trimmer lifecycle remains a regression scenario: record ownership, attach receipt and maintenance evidence, record a sale, answer current and historical questions, and replay sources without duplication. Add the multi-source reconciliation and quantity tests in the design.

## 3. Technology decisions

| Area | Selection | Notes |
| --- | --- | --- |
| UI | React + TypeScript + Vite | SPA, compiled for Docker deployment |
| Styles/components | Tailwind CSS + shadcn/ui + Lucide React | Standard, reusable UI system |
| Chat | assistant-ui (evaluate integration) | Provider-agnostic adapter; don't couple data layer to chat library |
| Graph visualization | Small interactive explorer in first release; evaluate Cytoscape.js | Graph explorer is not a substitute for browse/search |
| Charts/data tables | Recharts; TanStack Table and Query | Add as view complexity grows |
| Backend | Python + FastAPI + Pydantic | Hosting, auth, chat, uploads, static assets |
| MCP | Official `mcp` Python SDK v2, `MCPServer` | Streamable HTTP; mount in ASGI app; configure host lifespan |
| Database | PostgreSQL (C collation), psycopg 3 | Compose `db` service with a persistent volume; serialized writers via an advisory lock (replaced SQLite on 2026-10-22, see `docs/POSTGRESQL.md`) |
| ORM/migrations | SQLAlchemy + Alembic | Versioned schema; integration tests on actual PostgreSQL |
| Text retrieval | Owner-scoped word index (text array + GIN) | Exact all-words search and filtering |
| Semantic search | pgvector extension (enabled, unused) | Embeddings not necessary for initial vertical slice |
| Documents | Local filesystem + DB metadata | Hash content; restrict type and size; no executable uploads |
| Model integration | Provider adapter | Configurable cloud or local models; structured extraction |
| Jobs | In-process bounded job runner initially | Durable queue only when actually needed |
| Packaging | Multi-stage Docker build + Docker Compose | Vite static bundle copied into Python image; simple single-container start |
| Tests | pytest, Playwright, Vitest | Includes time-dependent and entity-match fixtures |

**Important MCP SDK note:** The planned target is SDK v2 with `MCPServer`; this planning document is not evidence of current release status. Verify installed API contracts against the official v2 documentation before authoring integration code. See https://py.sdk.modelcontextprotocol.io/ and https://py.sdk.modelcontextprotocol.io/run/asgi/ .

## 4. Architecture and boundaries

```
Browser: React/Vite SPA
   |                 
   |  HTTPS (auth, chat stream, uploads, UI state)
   v
FastAPI application
   ├── Auth/session handling, chat transport, document uploads
   ├── Server-side LLM agent (tool calling and streaming)
   └── MCP Server (Streamable HTTP endpoint for compatible external AI clients)
                    |
           Validated MCP tools
                    |
             Domain services
     ├── Memory ingestion and extraction
     ├── Entity resolution and deduplication
     ├── Temporal assertions and corrections
     ├── Retrieval and graph traversal
     ├── Approval and audit trail
     └── Document services
                    |
  PostgreSQL (pgvector) + private file storage
```

**Boundary rules:**
- MCP is the *domain-operation interface*: business reads/writes are described by typed MCP tools. The browser does not receive raw database credentials or execute SQL.
- HTTP endpoints for authentication, uploads, chat streaming, and compiled static assets are fine; the frontend's domain views can request data through an authenticated backend MCP proxy/adapter. Avoid duplicating business rules between HTTP and MCP.
- Domain services are plain Python, not coupled to FastAPI request objects, MCP decorators, or a specific LLM.
- A web chat needs its **own LLM agent loop** to decide which tools to call; exposing an MCP endpoint does not implement chat reasoning.
- An MCP server does not automatically observe conversations in ChatGPT/Claude. Information is persisted only when a connected client invokes ingestion, or an explicit import/integration feeds episodes into the system.
- Every write is authenticated, validated, authorized, and auditable. Destructive or ambiguous changes require confirmation.

## 5. Database model: evidence-backed temporal graph

Use string UUID/ULID identifiers; database foreign keys and indexes. Every private record and cross-record relationship must enforce authenticated owner scope, including derived indexes and jobs. The following is a conceptual model, not migration-ready DDL; add users, sessions, encrypted credentials, purchase/product/unit mappings, and reconciliation decisions as specified in the design. Suggested graph tables:

- `entities`: `id`, `kind`, `canonical_name`, `attributes_json`, `created_at`, `archived_at`.
- `entity_aliases`: `id`, `entity_id`, `alias`, `normalized_alias`, provenance.
- `episodes`: `id`, `source_type`, `source_identifier`, `raw_text`, `content_sha256`, `event_time`, `ingested_at`, `metadata_json`; idempotency key unique per source where appropriate.
- `assertions`: `id`, `subject_entity_id`, `predicate`, `object_entity_id` **or** `literal_json` (exactly one), `valid_from`, `valid_to`, `recorded_at`, `superseded_at`, `verification_status`, `confidence`, `reason`.
- `assertion_evidence`: `assertion_id`, `episode_id`, `evidence_span`, `evidence_excerpt` (source linking is many-to-many).
- `asset_records`: `entity_id`, `asset_category`, `manufacturer`, `model`, `serial_number`, `lifecycle_status`; physical instances must be distinct.
- `events`: `id`, `event_type`, `entity_id`, `occurred_at`, `recorded_at`, `details_json`, `source_episode_id`.
- `documents`: `id`, `sha256`, `path`, `original_filename`, `mime_type`, `size_bytes`, `uploaded_at`, metadata.
- `audit_log`: `id`, `actor_type`, `actor_id`, `operation`, `target_type`, `target_id`, `occurred_at`, `details_json`.
- `change_proposals`: pending operations/approval decisions for low-confidence, conflicting, or destructive actions.

When purchase capture is introduced, use **typed purchase/financial tables** for accounting (`transactions`, `merchants`, `accounts`, `subscriptions`, `purchase_lines`). Don't calculate financial totals by asking the LLM to add graph-literal strings. Store money as integer minor units + ISO currency or decimal-safe values.

**Time semantics:** `valid_from` and `valid_to` describe when a claim was true in the world; `recorded_at` and `superseded_at` describe when the system knew/accepted the claim. Unknown dates stay nullable, not invented. Preserve source episodes even after a claim is superseded, unless explicitly deleted for privacy.

## 6. AI ingestion and reconciliation pipeline

1. Receive message or file; authenticate origin; create a source episode with an idempotency key.
2. Apply deterministic parsing where possible; otherwise ask a model for schema-constrained candidate entities and assertions.
3. Normalize labels; match identifiers/aliases; retrieve top existing entity candidates.
4. Resolve identity conservatively; do not merge two serial-numbered objects on model similarity.
5. Check candidate facts against existing assertions and temporal intervals; identify conflicts and likely updates.
6. Prepare a **change proposal** and distinguish directly stated facts, external evidence, inference, and unknowns.
7. Auto-commit low-risk unambiguous information under configurable policy; seek user confirmation for merges, deletes, conflicts, and consequential actions.
8. Write the changes, evidence links and audit records in one database transaction.
9. Refresh FTS indexes and any affected entity summaries; return created/updated IDs and citations to evidence.

LLMs extract **candidate claims**; they do not write arbitrary SQL, fabricate sources, or decide financial/account-security consequences by themselves. Treat text from PDFs, receipts, web pages and external integrations as untrusted input, not operational instructions.

## 7. Initial MCP contract

Prefer compact typed operations, structured responses, pagination and stable IDs:

| Tool | Behavior |
| --- | --- |
| `memory_ingest(text, source_id?)` | Save source episode and extract/propose facts; return IDs and disposition |
| `memory_search(query, filters?, limit?)` | Search indexed text and known graph facts with sources |
| `memory_get_entity(entity_id)` | Attributes, current assertions, evidence, aliases, lifecycle |
| `memory_related(entity_id, predicates?, depth?, limit?)` | Bounded graph traversal; start with depth <= 2 |
| `memory_timeline(entity_id, from?, to?)` | Time-ordered facts and events |
| `memory_propose_correction(entity_id, fact_id, correction)` | Structured, reviewable change |
| `memory_approve_change(proposal_id)` | Validate/authenticate/commit approved proposal |
| `memory_list_assets(filters?, limit?, cursor?)` | Predictable list for UI and AI |
| `memory_source(episode_id)` | Retrieve original evidence subject to permissions |

Explicit deletion/export/backup operations should have their own guarded flows rather than hidden general-purpose database tools. The server must enforce access controls independently of whatever an AI agent promises.

## 8. Frontend information architecture

**Navigation:** Chat, Assets, Graph, Documents, Review, Settings; Overview and richer dashboards follow useful data. Chat is primary, and correction/recovery remain directly accessible.

**Navigation update, 2026-10-20:** Plan **Power Center** as a primary
destination for actual capabilities, connection health and data freshness, with
actionable recovery and precise capability-unlock explanations. Its Power Level
must measure useful readiness rather than count connected services. Make the
primary navigation panel dockable left/right/top/bottom and resizable, defaulting
left, with per-account remembered layout and accessible controls. This is separate
from the implemented right-default resizable assistant. Navigation docking is
implemented in v0.57.0; Power Center local readiness/health is delivered in v0.58.0.
Remote probing and richer live-model diagnostics remain future scope. See the linked design;
keep all existing destinations and private configuration workflows accessible.

**MVP views:**
- **Chat:** streamed answer, source citations, tool-activity states, confirmation dialogs for proposed changes.
- **Assets:** sortable/filterable list and search; can open an entity detail.
- **Entity detail:** current attributes, connected entities, ownership/condition, timeline, original evidence, correction action.
- **Overview:** counts, last memories saved, items needing review; do not manufacture financial totals or insights.
- **Settings:** Google sessions, individual provider/connector configuration, data export/backup and import preferences.

**UX principle:** AI performs structured data entry; users can always inspect, verify, correct, and undo the results. Charts and graph visualizations are *views* over validated records, not parallel stores of truth.

**Appearance requirement (2026-10-17):** Provide Light and Dark choices in app Settings, preserving each user's preference. The cream/sage/green reference in `.references/lifegather-soft-green-light-theme.png` is the approved visual direction for color and mood; adapt surfaces, text, borders, focus states, charts, and graph colors for readable contrast in each mode. Include theme support with the early usable UI, not as a late dashboard feature. Implemented in v0.10.0.

## 9. Development sequence and acceptance gates

The active sequence is AI-driven conversational tracking -> evidence intake and
recall -> demonstrated tracking reliability -> UI beautification. See
[phase acceptance criteria](docs/FEATURE_PLAN.md). The numbered stage list below
records the original delivery sequence, not an instruction to start banking,
reminders or every other deferred domain next.

User addition, 2026-10-17: provide email/password signup and sign-in alongside Google, with email verification and password recovery. This authentication milestone is implemented in source with fake-sender tests; real SMTP configuration/delivery remains pending. See [email authentication requirements](docs/EMAIL_PASSWORD_AUTH.md).

Source progress, 2026-10-17: Google login/session code, private settings/encrypted credentials, and the deterministic evidence-backed memory services are implemented with offline and two-user tests. The user reported local Google sign-in working. Credential storage needs an optional server key; it is not part of end-user login. Memory services include provenance, temporal corrections, search, bounded traversal, export, and tested database snapshots. Migration 0004 adds source-independent reconciliation with distinct product/purchase/unit identities, persistent review decisions, atomic retries, and reversible evidence reassociation. See `docs/RECONCILIATION.md` for the first slice and remaining limits. The private read-only MCP adapter now exposes owner-scoped recall and discovery inspection with protocol, concurrency, and authorization tests; see `docs/PRIVATE_MCP.md`. Writable tools, memory UI/HTTP adapters, chat, files, connectors, and jobs remain later work with their own authorization tests. See `docs/GOOGLE_LOGIN.md`, `docs/PRIVATE_SETTINGS.md`, and `docs/MEMORY_CORE.md`. Container builds/publication remain separately approved operations.

The original Phase 0 produced the frontend/backend Docker preview. Authentication, migrations, private memory services, and database snapshot/restore now have source-level acceptance tests. The preview does not provide a working memory UI or chat yet; future file storage also requires coordinated backup/restore coverage.

Follow the ordered stages and acceptance evidence in [the consolidated design](docs/superpowers/specs/2026-10-17-personal-discovery-design.md#delivery-order-and-gates):

1. Google registration, sessions, strict user isolation, and credential foundation.
2. Deterministic memory/evidence graph, temporal corrections, export, and tested backups.
3. Reconciliation with synthetic sources: create/enrich/review, distinct purchased units, idempotency, and reversible decisions.
4. Persistent private chat with provider selection, authenticated MCP, and execution/usage limits. The first [text-memory chat increment](docs/TEXT_CHAT.md) is implemented with local capture/search and optional OpenAI answers. The broader OpenAI/Claude streaming runtime remains planned.
5. Receipt/nameplate uploads, isolated extraction, discovery cards, correction, and persistent review queue.
6. Small interactive graph, evidence views, home/vehicle profiles, and useful recall. This completes the first useful release when its end-to-end acceptance tests pass.
7. Chat-requested email scans, followed by user-configured scheduled scans with progress, cancellation, recovery, and summaries.
8. Chat-requested sourced web research, after resolving external-data permission behavior.
9. Statement uploads followed by live bank sync, reconciled with existing purchase evidence.
10. Additional providers and separately scoped warranties, insurance exports, reminders, recalls, subscriptions, and dashboards.

Each stage needs a bounded implementation plan, relevant tests, migrations where applicable, and a passing local commit before proceeding. No live personal-data ingestion before ownership controls pass. No automatic GitHub builds; container rebuild/upload requires user approval.

## 10. Test and quality policy

- Every service operation has unit tests; every MCP tool has protocol-level tests.
- Maintain fixture-driven conversations for identity ambiguity, correction, sale/transfer, conflicting claims, duplicate ingestion, vague dates, no-confidence model output, and large text inputs.
- Key quality metrics: no unsupported facts in structured records; entity match accuracy; duplicate episode rate; current-state accuracy; historical answer accuracy; source-coverage rate; median search latency.
- A model adapter must be mockable so the entire graph engine runs in tests without network credentials.
- Review migrations and backups before schema changes; test restore, not only backup creation.
- Limit MCP graph depth, max response size, LLM cost/token budgets, ingestion batch size and file sizes.

## 11. Security and privacy requirements

- Start with private network access (localhost/Tailscale/reverse proxy), not a public unauthenticated MCP endpoint.
- Authorize tool calls in the backend and check Origin/Host for Streamable HTTP; use HTTPS and audience-validated tokens if remotely exposed.
- No model credentials, bank credentials, API tokens, secret keys or session cookies in the knowledge graph.
- Configure whether document content may be sent to external model providers. Disclose and allow private/local extraction paths later.
- Escape/validate untrusted extracted text; disregard embedded instructions in receipts, documents, or source episodes.
- Provide export, selective deletion and erasure of derived content/indexes/backups subject to stated retention policy.
- Use consistent PostgreSQL snapshots (the encrypted operator bundle inlines stored files); encrypt stored and off-site backups where possible.
- Do not silently create financial transactions or alter verified records based solely on a model's guess.

## 12. AI coding workflow: Claude Code / Codex

1. Store this plan at repo root; store durable coding rules in `AGENTS.md`; let Claude read `CLAUDE.md`.
2. Give the coding agent **one phase or small vertical task at a time**, not an instruction to build the entire system unsupervised.
3. Have it inspect the current repository and the SDK docs, describe minimal file changes, then implement.
4. Demand tests, an example invocation, migration implications and a change summary with each deliverable.
5. Run the tests locally and review diffs before accepting larger architectural changes.
6. Keep models/provider SDKs behind adapters; upgrade dependencies deliberately and lock working versions.
7. Commit at each passing acceptance gate. Avoid large speculative abstractions and autogenerated endpoints that bypass the domain layer.

**Next planning step:** Refine the [AI asset assistant design](docs/superpowers/specs/2026-10-21-ai-asset-assistant-design.md)
against current source and the [tracking-first feature plan](docs/FEATURE_PLAN.md).
The existing OpenAI, Claude and Gemini adapters, streaming/read-only recall,
private asset services and sourced correction history are already implemented.
Extend them with model-selected tools, necessary clarification and atomic coherent
asset changes; do not rebuild chat from historical plans. Dedicated banking and
proactive life-management automation remain deferred. `docs/FIRST_TASK.md` and
older milestone exclusions are historical context, not current missing scope.

## 13. References

- MCP Python SDK v2: https://github.com/modelcontextprotocol/python-sdk
- MCP SDK in an ASGI host: https://py.sdk.modelcontextprotocol.io/run/asgi/
- MCP security specification: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- Vite guide: https://vite.dev/guide/
- shadcn/ui Vite setup: https://ui.shadcn.com/docs/installation/vite
- PostgreSQL backup: https://www.postgresql.org/docs/current/backup.html
- Codex repository instructions: https://developers.openai.com/codex/guides/agents-md
- Claude Code `CLAUDE.md`: https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts

Source increment v0.18.0: the [Memories library](docs/MEMORIES.md) now supports browsing/searching saved sources, current/history filters and direct note capture. Shared asset/file evidence views preserve derived-source labels and deletion notices. Broader receipt extraction remains ahead.
