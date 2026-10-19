# Shared change provenance and field history

Baseline main efde251 / v0.43.0 / migration 0021. Private record export has a
separate kickoff branch reserving v0.44.0; preserve it, avoid its files, and resolve
version/export allowlist overlaps before merge. Target the next available minor
(currently v0.45.0), not the export branch's planned version.

Approved scope: additions/corrections retain their source, actor workflow, time,
AI attribution where available, and accessible field history. Reuse existing
immutable sources/facts and audit records, not a competing history store.

1. Add nullable structured provenance JSON to existing audit events (migration
   0022). Legacy events stay unknown, without inferred/backfilled human attribution.
   Server-owned ContextVars capture interface, initiator, method, provider/model
   and related saved request/job/review IDs. Public input schemas/fingerprints stay
   unchanged; submitted headers/document text cannot choose audit attribution.
2. Classify web forms, chat capture/AI extraction, explicit review/correction,
   external MCP clients and scan workers honestly. A web/external client is not
   proof of a human or AI. Scheduler enqueue persists its initiation; workers
   restore that persisted origin and AI discovery records its selected adapter.
3. Private paged field-history service/HTTP read, with current/previous exact values,
   statement status, valid/recorded times, evidence and audit provenance. Never call
   a user-stated value independently verified or label a review action as proof of
   a human. Preserve concurrent alternatives rather than invent a replacement link.
4. Shared field-history component in Profiles, Assets and Graph. Explicit load,
   bounded pages, source references, errors/retry and cancellation on context change.
   Keep existing corrections and specialised source/action histories intact.
5. Verify two-user isolation, old/migrated data, atomic rollback/idempotent retry,
   correction chronology, context reset/concurrency, AI/manual/import/scheduled
   origins, HTTP/MCP boundaries, paging and UI races. Run relevant full checks,
   refresh code graph, commit/push/PR/merge/cleanup and release per standing policy.

No asset templates, new vehicle forms, odometer subsystem, free-form agent writes,
live mailbox/model calls, credential logging or retroactive guesses in this slice.

Implementation acceptance: v0.45.0 / migration 0022. Backend Ruff/format/strict
mypy pass; full backend 452 tests pass, with 18 focused HTTP/MCP/origin tests
rerun after explicit MCP adapter attribution. Frontend lint/format/production
build and 198 interaction tests pass. Both Compose configurations validate.
Legacy upgrade fixtures seed the historical audit format instead of incorrectly
using a new ORM column against an old schema. Code-only Graphify and HTML refreshed
(2797 nodes / 11173 edges); AssetsPanel has the existing parser-coverage warning,
so TypeScript/build/tests remain authoritative. No live provider/mailbox calls.
