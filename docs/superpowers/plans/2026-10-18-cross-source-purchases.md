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

- [x] Extract a shared unchanged canonical purchase identity resolver; service tests
  first for four source roles, exact identity reuse and payment refusal.
- [x] Migration0020 adds append-only owned purchase-evidence revisions, stable request
  identities and current-root uniqueness. Add bounded read/write/history service,
  exact typed money/date, conflict reporting and move/withdraw/replay guards.
- [x] Add owner/CSRF/body-limited HTTP and explicit MCP evidence adapters; keep chat's
  read tools unchanged. Test isolation, current source validation, restored database,
  concurrent request and migration preservation.
- [x] Add Purchases view/source chooser/form/evidence history, accessible loading,
  explicit user actions, frozen failed-write retry and stale-read guards. Observe
  failing interaction tests before implementation.
- [x] Full backend/frontend lint/type/format/tests/builds; graph refresh, final clash
  check, v0.37.0/changelog/docs, commit/push/PR/merge/cleanup. Do not run a live scan
  or modify an existing deployment during verification.

The initial commit/push publishes this scope before code, following the early
visibility rule. Source review/correction is the bounded first slice of #3;
broader transaction allocation and automatic extraction are not claimed complete.

Verification: observed missing-module/UI failures before implementation. Exact-ID
prefix test failed and was corrected to require complete source identifiers. Full
suite initially found a stale MCP read-only-tools allowlist; updated its two explicit
write exceptions and asserted their non-read-only annotations. Final full suite:
363 backend / 136 frontend tests pass. Ruff lint/format, strict mypy (182 files),
TypeScript/Oxlint/Prettier, frontend and wheel builds pass. Nine purchase tests cover
four-source grouping, unchanged physical-item count, existing/forward identity reuse,
payment-only refusal, exact amounts/dates, corrected source conflicts, move/withdraw/
replay/history, tenant constraints, concurrent replay, migration and snapshot recovery.
UI covers explicit selection/save, identical retry, stale withdrawal and late reads.

Final clash check: main remains cee6b2d, no open PRs/competing remote feature branches,
v0.37.0 and migration0020 unused on main. Root-only diff review confirms existing
receipt fingerprints and financial lines untouched; only exact purchase resolution
is shared. No live provider calls, personal-data import, image build/upload or
deployment. Advanced allocation/refunds, automatic extraction and whole-record
merging remain outside this slice. Source graph/HTML refreshed before delivery.
