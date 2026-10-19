# Cross-source purchase evidence — first usable slice

Extend the existing reconciliation Purchase/OrderRef identity rather than create
a competing purchase table. A user explicitly reviews a saved source and attaches
order, receipt, shipment or payment evidence to one owned purchase. Exact retailer,
account scope and order ID reuse the same canonical purchase. Account scope is the
user's private account label, not a claim inferred from document contents.

Creating/resolving by order identity requires retailer/order ID in an exact source
quote. Selecting an existing purchase is an explicit user association with a reason;
it may be used for a payment lacking an order number. Payments cannot create a new
purchase or imply item contents, delivery or ownership. Never match on amount/date
or item name alone. No asset/line/entity/fact write occurs when attaching evidence.
Existing OrderRef-backed physical-item associations remain readable and unchanged.

Keep one current association per source root in this slice; corrections create
immutable revisions and can move evidence to another purchase or withdraw it.
Original sources, previous links, exact quotes, reasons, recorded time and optional
source-supported event date remain inspectable. Optimistic heads and request replay
protect concurrent/lost-response writes, including reattachment after withdrawal.
Corrected/deleted source versions remain visibly historical and cannot justify a
new attachment. Withdrawal remains possible after original deletion/correction.

Optional order/receipt totals or payment amounts use supported exact currency/minor
units and exact currency-coded source quotes. Never sum repeated documents or treat
multiple payment claims as accounting balances. Show differing current order totals
as a conflict, excluding unavailable/stale evidence. Payment allocation, split/combined
charges, refunds, returns, shipment line quantities and automatic extraction need
later bounded increments. No bank connector or live AI/network requests here.

Add a Purchases view: paginated purchase list, owned source search/selection and
original-text preview, attach/correct/withdraw form, paged evidence/history,
explicit conflict/historical labels and existing linked item inspection. HTTP/MCP
are thin authenticated adapters; MCP writes retain explicit human-review semantics
and are not added to the read-only product chat runtime.

Acceptance: canonical identity reuse with existing reconciliation, cross-user scope,
exact quotes/money/date, four-source grouping with no duplicate assets, no payment-only
creation, immutable move/withdraw/retry/history, stale-source/refusal, concurrency,
bounded paging and snapshot/migration recovery. UI tests prove explicit actions,
request/revision retry and no implicit writes on navigation. Full checks before release.
