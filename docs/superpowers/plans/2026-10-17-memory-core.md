# Evidence-backed memory core implementation plan

Feature #3 in the ordered feature list. Main chat implementation only; preserve unrelated document edits. Google login was reported working by the user on 2026-10-17. No Docker rebuild/upload.

## Deliverable and boundaries

Build framework-independent Python services and migration `0003_memory_core` over the private SQLite store. Every entity, source, alias, fact, evidence link, audit entry, search, and traversal is scoped to an authenticated `Account`; composite owner/ID foreign keys prevent cross-owner links even if service validation fails. No new HTTP/MCP adapter or UI data-entry path yet: authenticated MCP and chat come in their later stage. No model calls, receipt extraction, automatic entity merging, files, purchases/accounting, or live connectors in this slice.

Sources preserve original text, content hash, source type/namespace/external ID, event time, and recorded time. A stable external ID replay reuses the source; changed content under that ID is a conflict, not an overwrite. Without an external ID, exact content plus source context/time is idempotent. Explicit entity/fact operation keys make write retries safe. Matching labels/models never merges objects.

Facts carry a subject, predicate, exactly one literal or related entity, verification status, original evidence, nullable valid-world date bounds, and system recorded/superseded timestamps. Corrections create new versions with new evidence and audit history; old values remain available through system-time queries. Dates have day precision in this slice; unknown dates remain null. Historical date queries include only facts with known starts and matching intervals, avoiding false certainty about unknown dates.

## Tasks and tests

1. Write failing tests for the sourced trimmer lifecycle, corrections/as-of queries, duplicate source/operation replay, two identical physical items, aliases, and unknown dates. Add typed input/result schemas, owner-constrained models, migration and transactional service methods. Reject cross-user source/entity/fact IDs and conflicting reuse of operation IDs.
2. Add literal-token FTS5 search and bounded one/two-hop traversal. Test invalid/oversized inputs, graph/query limits, cross-owner IDs and search isolation, and transactional rollback of rejected assertions. Index updates must occur in the same transaction as writes.
3. Add paginated owner-only export and a separate operator-only SQLite snapshot helper using the online backup API and no-overwrite destination creation. Test backup restore, migration preservation of login/settings, persistence and source evidence consistency. No backup HTTP endpoint and no secret-vault export.
4. Document exact semantics and limitations, run backend checks plus existing UI tests, inspect packaged migrations, refresh the source-code graph, and commit the passing slice. The core is ready for reconciliation and later thin adapters; do not label the chat UI functional yet.

## Acceptance

An offline fixture can record a purchase statement, attach maintenance, record a sale, distinguish current/historical ownership, inspect all supporting text, replay operations without duplicates, retain two separately identified identical items, and deny every cross-user access/link. Restored snapshots reproduce those results without credentials or an LLM.

## Completion evidence

Verified 2026-10-17: 45 backend tests and 11 existing UI tests pass; Ruff lint/format and mypy pass. The built wheel contains memory services and migration 0003. Source graph refreshed with code-only extraction (531 nodes, 1214 edges). No Docker rebuild/upload or source push performed. Thin memory adapters and UI remain later milestones.
