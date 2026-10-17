# LifeGather — Initial Product and Engineering Plan

**Status:** Draft / implementation-ready scope for the first iteration  
**Date:** 2026-10-16  
**Project name:** LifeGather (working brand; domain and trademark clearance not yet completed)  
**Deployment:** Private, self-hosted Linux server using Docker Compose  
**Development mode:** AI-assisted, using Claude Code and/or Codex with reviewable, test-driven increments

## 1. Product vision

LifeGather is a private, AI-first, persistent personal-memory application. Its job is not merely to store a collection of personal lists. It should gradually accumulate a source-backed understanding of the user's life: possessions, places, organizations, purchases, repairs, events, conversations, expenses, subscriptions, vehicles, warranties, policies, and documents.

The primary control surface is natural-language chat, backed by Model Context Protocol (MCP) tools. The web UI provides search, inspection, corrections, dashboards, timelines, and an eventual knowledge-graph visualization.

**Primary product principle:** Keep an auditable distinction between (a) what the user or a document asserted, (b) what has been verified, (c) what the AI inferred, and (d) what is unknown.

**Guiding example:** A user says they bought a Husqvarna trimmer. Later they submit a receipt, mention a repair, and ultimately sell it. LifeGather should resolve those references to the same asset, maintain historical ownership and maintenance events, and answer questions with citations back to the underlying messages/receipts. It must not fabricate a price, serial number, exact date, or sale if none is supported.

## 2. Scope: thin vertical slice first

### MVP (first releasable personal prototype)

1. Single-user authenticated local/private deployment.
2. Functional chat page with a configurable model provider and streamed response.
3. MCP tools to ingest a user statement, search memories, read an entity, list relationships, and correct a fact.
4. SQLite-backed entities, aliases, source episodes, assertions, evidence links, lifecycle events, and audit entries.
5. AI extraction of proposed entities and facts from a statement using schema-validated JSON.
6. Conservative entity resolution: exact identifiers, aliases and known relationships first; ambiguous cases go to review.
7. Temporal facts: track when something was true *and* when LifeGather learned it.
8. FTS5 text search plus relationship traversal; no embeddings required for the first demo.
9. A browseable asset/entity list, detail view, memory timeline, and source/evidence view.
10. Persistent Docker volumes, repeatable migrations, backups, health check, unit/integration tests.

### Not MVP

Automatic Plaid/banking ingestion; email inbox monitoring; full accounting; recurring payment detection; graph-wide AI consolidation; multi-user accounts; public SaaS; vector DB; Graphiti, Neo4j or FalkorDB; advanced Cytoscape layouts; mobile app; continuous autonomous monitoring. These are future milestones, not prerequisites.

### First end-to-end demo

- Submit: “I own a Husqvarna 525L trimmer that I purchased from Home Depot in 2024.”
- Query: “What trimmers do I own?” → returns existing trimmer with evidence; price is *unknown*.
- Submit: “My Husqvarna weed eater needed its carburetor cleaned.” → links maintenance to the existing asset; no duplicate.
- Query: “What maintenance did I mention for my trimmer?” → returns the statement and evidence.
- Submit: “I sold that trimmer in July 2025.” → currently owned = false, with sale event/history preserved.
- Query: “Did I own it in June 2025?” → yes, if timelines support it.
- Replay prior episode → no duplicate entities, events, or financial entries.

## 3. Technology decisions

| Area | Selection | Notes |
| --- | --- | --- |
| UI | React + TypeScript + Vite | SPA, compiled for Docker deployment |
| Styles/components | Tailwind CSS + shadcn/ui + Lucide React | Standard, reusable UI system |
| Chat | assistant-ui (evaluate integration) | Provider-agnostic adapter; don't couple data layer to chat library |
| Graph visualization | Cytoscape.js, after core MVP | Graph explorer is not a substitute for browse/search |
| Charts/data tables | Recharts; TanStack Table and Query | Add as view complexity grows |
| Backend | Python + FastAPI + Pydantic | Hosting, auth, chat, uploads, static assets |
| MCP | Official `mcp` Python SDK v2, `MCPServer` | Streamable HTTP; mount in ASGI app; configure host lifespan |
| Database | SQLite, WAL mode, foreign keys | Local bind-mounted persistent volume; single primary writer |
| ORM/migrations | SQLAlchemy + Alembic | Versioned schema; integration tests on actual SQLite |
| Text retrieval | SQLite FTS5 | Exact, ranked text search and filtering |
| Semantic search | Optional sqlite-vec later | Embeddings not necessary for initial vertical slice |
| Documents | Local filesystem + DB metadata | Hash content; restrict type and size; no executable uploads |
| Model integration | Provider adapter | Configurable cloud or local models; structured extraction |
| Jobs | In-process bounded job runner initially | Durable queue only when actually needed |
| Packaging | Multi-stage Docker build + Docker Compose | Vite static bundle copied into Python image; simple single-container start |
| Tests | pytest, Playwright, Vitest | Includes time-dependent and entity-match fixtures |

**Important MCP SDK note:** Version 2 is the current stable SDK line as of this plan, replacing v1 `FastMCP` with `MCPServer`. Verify installed API contracts against the official v2 documentation before authoring integration code. See https://py.sdk.modelcontextprotocol.io/ and https://py.sdk.modelcontextprotocol.io/run/asgi/ .

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
       SQLite DB + document directory
```

**Boundary rules:**
- MCP is the *domain-operation interface*: business reads/writes are described by typed MCP tools. The browser does not receive raw database credentials or execute SQL.
- HTTP endpoints for authentication, uploads, chat streaming, and compiled static assets are fine; the frontend's domain views can request data through an authenticated backend MCP proxy/adapter. Avoid duplicating business rules between HTTP and MCP.
- Domain services are plain Python, not coupled to FastAPI request objects, MCP decorators, or a specific LLM.
- A web chat needs its **own LLM agent loop** to decide which tools to call; exposing an MCP endpoint does not implement chat reasoning.
- An MCP server does not automatically observe conversations in ChatGPT/Claude. Information is persisted only when a connected client invokes ingestion, or an explicit import/integration feeds episodes into the system.
- Every write is authenticated, validated, authorized, and auditable. Destructive or ambiguous changes require confirmation.

## 5. SQLite model: evidence-backed temporal graph

Use string UUID/ULID identifiers; database foreign keys and indexes. Suggested tables:

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

In later phases, use **typed financial tables** for accounting (`transactions`, `merchants`, `accounts`, `subscriptions`, `purchase_lines`). Don't calculate financial totals by asking the LLM to add graph-literal strings. Store money as integer minor units + ISO currency or decimal-safe values.

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

**Navigation:** Chat, Overview, Assets, Memories, Graph (later), Documents (later), Settings.

**MVP views:**
- **Chat:** streamed answer, source citations, tool-activity states, confirmation dialogs for proposed changes.
- **Assets:** sortable/filterable list and search; can open an entity detail.
- **Entity detail:** current attributes, connected entities, ownership/condition, timeline, original evidence, correction action.
- **Overview:** counts, last memories saved, items needing review; do not manufacture financial totals or insights.
- **Settings:** local auth, provider configuration, data export/backup and import preferences.

**UX principle:** AI performs structured data entry; users can always inspect, verify, correct, and undo the results. Charts and graph visualizations are *views* over validated records, not parallel stores of truth.

## 9. Development sequence and acceptance gates

### Phase 0 — Repository, repeatable environment and policies
- Create `frontend/`, `backend/`, `docs/`, `tests/`, Dockerfile, Compose and `.env.example`.
- Scaffold React/Vite/TypeScript and FastAPI with `/health`.
- Establish lint, formatting, type checks, unit tests and CI-equivalent local scripts.
- Set up non-root Docker, persistent private data volume, secret handling, migrations, safe startup and backup command.
- **Done when:** Docker can build and run the app; UI loads; backend health passes; database survives restart; secrets remain out of git.

### Phase 1 — Deterministic graph core (no LLM dependency)
- Implement schema/migration, services for create/read/search/update entities and assertions, provenance and temporal facts.
- Add idempotent source ingestion and alias handling.
- Add FTS5 index and retrieval with constrained query limits.
- Add test fixtures for corrections, as-of queries, duplicate episodes, and multiple identical objects.
- **Done when:** An offline test can reconstruct the full trimmer lifecycle and produce correct current vs historical answers.

### Phase 2 — MCP and agent-assisted ingestion
- Add authenticated MCPServer v2 Streamable HTTP tool handlers delegating to domain services.
- Add one configurable model adapter and schema-validated extraction + entity-resolution proposal flow.
- Add chat endpoint and server-side tool-calling loop with per-turn limits and approval barriers.
- **Done when:** A message can create a sourced trimmer memory, a second message updates it, and MCP queries retrieve it without duplicate records.

### Phase 3 — Usable React interface
- Add chat, assets list, detail/timeline, evidence viewer, review queue and correction flow.
- Run Playwright tests for save, search, inspect, correct, and restart persistence.
- **Done when:** A user can complete the above trimmer scenario from the web UI without touching SQL or a developer console.

### Phase 4 — Receipts and document relationships
- Add restricted file upload, hashing, dedupe, document extraction and human review.
- Link receipt line-items to owned equipment and purchase events; mark uncertain association for review.
- **Done when:** Uploading the same receipt twice doesn't duplicate purchases, and all amounts trace to the source.

### Phase 5 — Expansion once quality is established
- Add subscriptions, vehicles, policies, maintenance, accounts, recurring expenses and scheduled analysis in discrete domain slices.
- Evaluate semantic embeddings, knowledge-summary consolidation and Cytoscape graph exploration based on measured retrieval needs.
- Defer bank/email connectors and autonomous ingestion until consent, permissions, idempotency and auditability are solid.

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
- Use SQLite online backup/VACUUM INTO, coordinate file snapshot of documents; encrypt stored and off-site backups where possible.
- Do not silently create financial transactions or alter verified records based solely on a model's guess.

## 12. AI coding workflow: Claude Code / Codex

1. Store this plan at repo root; store durable coding rules in `AGENTS.md`; let Claude read `CLAUDE.md`.
2. Give the coding agent **one phase or small vertical task at a time**, not an instruction to build the entire system unsupervised.
3. Have it inspect the current repository and the SDK docs, describe minimal file changes, then implement.
4. Demand tests, an example invocation, migration implications and a change summary with each deliverable.
5. Run the tests locally and review diffs before accepting larger architectural changes.
6. Keep models/provider SDKs behind adapters; upgrade dependencies deliberately and lock working versions.
7. Commit at each passing acceptance gate. Avoid large speculative abstractions and autogenerated endpoints that bypass the domain layer.

**First assignment to give an agent:** See `docs/FIRST_TASK.md` for the exact Phase 0 kickoff prompt. After that, implement Phase 1 with no LLM integration. The priority is a trustworthy memory store, not a flashy mock dashboard.

## 13. References

- MCP Python SDK v2: https://github.com/modelcontextprotocol/python-sdk
- MCP SDK in an ASGI host: https://py.sdk.modelcontextprotocol.io/run/asgi/
- MCP security specification: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- Vite guide: https://vite.dev/guide/
- shadcn/ui Vite setup: https://ui.shadcn.com/docs/installation/vite
- SQLite backup: https://www.sqlite.org/backup.html
- Codex repository instructions: https://developers.openai.com/codex/guides/agents-md
- Claude Code `CLAUDE.md`: https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts
