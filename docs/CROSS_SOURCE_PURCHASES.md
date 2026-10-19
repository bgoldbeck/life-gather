# Cross-source purchase evidence (v0.37.0)

Open Purchases, choose saved evidence and review its association. Order confirmations,
receipts, shipment notices and payment evidence can all describe one canonical purchase.
Use the same retailer, exact private account label and exact order ID to resolve the
existing identity. Retailer/order identifiers must occur as complete values in the
supporting source quote. Account labels distinguish your own retailer accounts; use
them consistently. No name/amount/date-based physical-item merge is performed.

Alternatively choose an existing purchase explicitly and explain the association.
This supports a payment source with no order number. Payment evidence cannot create
a purchase or establish what was bought. Shipment evidence does not establish delivery
or current ownership. Attaching any source only writes purchase associations: no asset,
product, line, graph fact or ownership write occurs. Existing OrderRef-backed item
reconciliation shares this canonical identity and its existing linked items can be
opened in the graph. Existing receipt-line totals and identity decisions are preserved.

Optional order/receipt totals and payment amounts require exactly one currency-coded
passage, such as `USD 349.00`, within the exact evidence quote. Supported currencies
match receipt details: USD/EUR/GBP/CAD/AUD/JPY. JPY uses whole yen; others use two decimal
places. Optional event dates require one exact matching YYYY-MM-DD passage within
the evidence quote. Unknown dates stay unknown. Recorded time is stored separately.
Amounts are independent source claims, not a bank ledger; do not add confirmations,
receipts and payment notices together. Conflicting current order/receipt totals are
shown without selecting a winner. Payments are not compared to order totals because
they may be partial; no balance or refund allocation is inferred.

Each saved source root has one current purchase association in this slice. Correcting
its target/role/claims or withdrawing it appends a revision with the reason and exact
old/new source references. Old associations remain in history, including moves between
purchases. Explicit reattachment requires the withdrawn head's current ID. Retrying a
lost response reuses the same request identity and never reintroduces a withdrawn link.
A concurrent update requires refreshing and reviewing the current head.

Corrected source versions and deleted photo/PDF originals remain historical. Their
claims are excluded from current total comparison and cannot support a new association;
withdrawal remains possible. Original/corrected evidence is still available through
the existing Memories, Photos and Documents workflows subject to deletion policy.
This feature is not a full accounting ledger or a guarantee that every document has
been classified correctly. Users explicitly choose the role and association.

The list and evidence/history views are paged. Fifty current sources per purchase and
the first twenty existing linked items are supported. Multi-order documents need a
later source-fragment increment. Sources without order identity need an explicit user
target; ambiguous cases are not automatically matched. No AI or connector request is
made by this workflow. Automatic email receipt extraction, allocations/split payments,
refunds, shipment quantities and complete-record merging remain separate features.

Private MCP exposes `purchase_list`, `purchase_get`, `purchase_evidence_history` and
explicitly human-reviewed `purchase_evidence_save` / `purchase_evidence_withdraw`.
These writes are not added to the product chat's read-only tool runtime. HTTP writes
require authenticated owner and CSRF; all references and database foreign keys are
owner-scoped. Schema migration0020 is additive. Operator SQLite snapshots preserve
source associations and full history; keep ordinary deployment backups before upgrade.
