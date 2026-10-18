# Source-independent reconciliation: first backend slice

Continue the approved discovery roadmap after the memory core. Implement in the main chat only. Preserve unrelated edits; no provider calls, dependencies, Docker builds, uploads, or automatic pushes.

## Contract

A validated discovery references an existing owned source and a verbatim excerpt. It explicitly supplies item/quantity information, optional manufacturer/model/serial, and optional retailer/account/order/line identity. Payment-only evidence and mentions never create inventory. Quote membership is a structural check, not proof that an extractor understood a document; extraction is a later isolated stage.

Keep source observations, product models, purchase orders, purchase lines, physical entities, and versioned reconciliation decisions distinct. Exact serial identifiers are scoped to manufacturer; order identities include merchant and account scope, line and unit ordinal. Product similarity only suggests candidates. Clear purchase/possession discoveries create inferred ownership; an ambiguous match creates a persistent review case without another asset. Different anchored purchases of the same product remain separate. Conflicting product/quantity/serial identifiers require review. Unknown purchase dates stay unknown. No monetary amounts or accounting in this slice.

All decision writes, graph facts, inventory bindings, evidence, audit records and FTS changes share one serialized transaction. Replays and concurrent submissions are idempotent per user/source/item key. Decision changes require an expected current decision, preserve predecessors, and can be undone by another recorded decision. Undo retires only decision-owned facts; it retains original sources and physical entities. Inventory is the set of active decision bindings, not every historical asset entity. Reassociation covers evidence discovered through this service, not a general-purpose merge of arbitrary pre-existing graph entities.

## Work and verification

1. Add failing synthetic tests for create/enrich/review, receipt/shipping/manual source order, distinct units/quantities, payment-only input, rejected replays, and two-user isolation.
2. Add migration 0004, typed inputs/results and framework-independent services. Reuse memory entity/fact writes inside the caller transaction; retain existing public methods.
3. Test decision correction/undo, stale/repeated requests, conflicts, rollback, concurrent replay, persistence and snapshot restore. Owner-constrained FKs cover every cross-record link; queries and pages are bounded.
4. Document exact limitations. Run backend and existing frontend checks, package migration inspection, source graph refresh, then create a local commit. Stop before chat/MCP or upload UI.

## Completion evidence

Verified 2026-10-17: 62 backend tests (17 reconciliation cases) and 11 existing UI tests pass; Ruff lint/format and mypy pass. Wheel packaging includes migration 0004 and reconciliation modules. Migration/ORM comparison found no reconciliation schema drift. Code-only source graph refreshed: 620 nodes, 1597 edges. Synthetic tests include ownership correction conflicts, excluded identities, rollback, two-user FKs, clock reversal, concurrent sources, migration preservation and restored inventory. No live ingestion, UI adapters, Docker rebuild/upload, source push or merge performed.
