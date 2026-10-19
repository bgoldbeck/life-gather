# Cross-source purchase evidence implementation

Root-only execution using executing-plans and TDD. No subagents.
Spec: ../specs/2026-10-18-cross-source-purchases-design.md
Goal: connect reviewed order/receipt/shipment/payment sources to the existing
canonical purchase identity, without duplicating assets or inventing accounting.
Architecture: framework-independent service, additive SQLite migration 0020,
authenticated HTTP/MCP adapters, responsive React Purchases view.

Clash preflight: current main cee6b2d, app v0.36.0, migration0019; no open PRs or
other remote feature branches. Existing reconciliation Purchase/PurchaseLine,
OrderRef and IdentityMatcher already deduplicate scoped order lines. ReceiptDetails
already stores sourced line money; preserve it and its replay fingerprints. Add
source evidence instead of replacing these contracts. Parked historical worktrees
are not implementation baselines. Two unrelated main documentation edits remain.

- [ ] Extract a shared unchanged canonical purchase identity resolver; service tests
  first for four source roles, exact identity reuse and payment refusal.
- [ ] Migration0020 adds append-only owned purchase-evidence revisions, stable request
  identities and current-root uniqueness. Add bounded read/write/history service,
  exact typed money/date, conflict reporting and move/withdraw/replay guards.
- [ ] Add owner/CSRF/body-limited HTTP and explicit MCP evidence adapters; keep chat's
  read tools unchanged. Test isolation, current source validation, restored database,
  concurrent request and migration preservation.
- [ ] Add Purchases view/source chooser/form/evidence history, accessible loading,
  explicit user actions, frozen failed-write retry and stale-read guards. Observe
  failing interaction tests before implementation.
- [ ] Full backend/frontend lint/type/format/tests/builds; graph refresh, final clash
  check, v0.37.0/changelog/docs, commit/push/PR/merge/cleanup. Do not run a live scan
  or modify an existing deployment during verification.

The initial commit/push publishes this scope before code, following the early
visibility rule. Source review/correction is the bounded first slice of #3;
broader transaction allocation and automatic extraction are not claimed complete.
