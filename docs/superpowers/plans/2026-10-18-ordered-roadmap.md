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

- Protect unrelated edits and unfinished worktrees. No live personal-data ingestion,
  paid model calls or externally configured services without configured permission.
- Source delivery is authorized. Respect the user's most recent local-only Docker
  choice; builds/uploads and running-container changes remain separate operations.
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
9. Photo handling: chat attachments, individual link removal, event galleries and
   graph navigation, preserving original privacy/deletion contracts.
10. Email connections and requested scans: owner-scoped credentials, requested scope,
    receipt discovery/reconciliation, no arrival-triggered ingestion.
11. Scheduled scans: durable timezone-aware jobs, progress, cancellation, recovery,
    deduplication, pause/edit and summaries.
12. Sourced requested web research: explicit scope and external-data permission,
    dated sources, no unsupported identity/ownership assertions.
13. Bank statements then live sync: deterministic exact-money tables and shared
    purchase reconciliation; verify service access/cost before configuring it.
14. User-facing export/backup/restore/privacy controls over the existing owner-scoped
    services, with clear scope and retention and tested recovery boundaries.
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
