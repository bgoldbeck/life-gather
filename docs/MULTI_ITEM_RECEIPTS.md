# Reviewed multi-item receipts

Version 0.19.0 adds a bounded receipt review to saved notes, reviewed PDF text and
saved photo transcriptions. Open a current note in Memories, choose **Review
multiple items from this note**, select an owned AI connection/model, then press
**Suggest receipt items**. Selecting a note alone never calls a provider.

The shared OpenAI, Claude and Gemini runtime requires explicit external-AI consent,
uses existing request/token/time limits, and sends only the selected saved text.
Embedded document instructions are untrusted data. No model write tools are used.
Live provider extraction remains unverified; synthetic adapters exercise the flow.

## Review and evidence

- At most eight distinct quoted item lines and twenty physical units per receipt.
- Suggestions remain unverified mentions. Explicitly state purchase or possession,
  select each included line, edit details if needed, and check it for duplicates.
- Choose new records or distinct existing records for every unit. Matching product
  names never automatically merge physical items. Reliable identifiers block an
  incompatible new-record choice; serial-number items have quantity one.
- Every item quote must occur exactly in the current saved source. Manufacturer,
  model and serial must be source-grounded using existing proposal validation.
  Multiple units require an exact quantity passage within that item's quote:
  `Qty 2`, `quantity: 2`, `count 2`, or `2 units/pcs/pieces` (case-insensitive).
  Missing quantity defaults to one and still requires human review. Other receipt
  quantity formats need a corrected note before use; conflicting quantities fail.
- Exclude irrelevant lines. Confirmation checks every selected line again before
  writing anything and commits the entire selection in one transaction. Repeating
  the same confirmation returns the same result. A lost response freezes the review
  for an exact retry; later edits require fresh duplicate checks.
- Drafts persist in Review â†’ Receipts. The source links back to the receipt review.
  Single-item and receipt reviews cannot accept the same source twice. A rejected
  draft stays in history; use a corrected note version to propose revised content.
- Corrections retain the original source, stale the draft and prevent acceptance.
  Original photo/PDF deletion also prevents acceptance. Rejection remains possible.
  Accepted facts retain source evidence, and photo attachments follow each unit.

Receipt AI extraction does not infer prices, currencies, purchase dates, totals,
taxes, refunds, warranties or accounting entries. Version 0.20.0 adds optional,
human-entered typed purchase claims below; no monetary values are stored as
free-form graph accounting facts.
It does not automatically import email, OCR scanned PDFs or contact providers merely
because a file was uploaded. Review establishes a stated relationship, not independent
verification of present ownership.

## Service and storage

Framework-independent `ReceiptService` owns validation and atomic reconciliation.
Authenticated HTTP `/api/receipts/{id}`, `/preview`, `/review` and typed MCP
`receipt_get`, `receipt_preview`, `receipt_review` use the same service and owner
scope. Write adapters enforce existing session, origin and CSRF checks. MCP receipt
operations are not exposed to the chat model's read-tool allowlist.

Migration `0014_receipt_proposals` adds an owner/source-constrained private table
for original drafts, reviewed values, request replay identity, result links and
recorded/reviewed times. No existing graph/source rows are rewritten. Snapshot
restore and migration head are tested. No new runtime dependency or deployment.


## Purchase details (v0.20.0)

After confirming a purchased receipt line, open its receipt review from source
evidence. Each included purchase has an optional purchase-details editor. Possession
statements and excluded lines do not qualify. This works without AI or provider
permission and can be added to receipts confirmed before the upgrade.

Enter a **USD line total** with exactly two decimal places, for example `49.90`,
and copy a source passage containing the exact reviewed item quote plus one
`Line total: USD 49.90` passage. USD must be explicit: `$` alone is ambiguous.
Supported totals range from `0.00` to `999999999.99`. There is no float conversion:
`49.90` becomes 4990 integer cents. This is the total for the entire line across
its reviewed quantity; it is never multiplied or divided into a guessed unit price.

Optionally enter a real `YYYY-MM-DD` purchase date and its exact labeled
`Purchase date: YYYY-MM-DD` passage from the same saved source. Delivery dates,
file timestamps, locale-dependent dates and unstated dates are not substituted.
These conservative labels are the supported first slice; other currencies and
receipt formats remain unknown until separately supported. If correcting source
text, add only what you can support: a correction is itself a user statement.

Every save requires a revision reason and the current revision ID. Competing edits
fail rather than overwrite; reload before retrying a correction. A lost response
freezes fields for an exact request retry. Clear both values and quotes to withdraw
an earlier claim to unknown; earlier values remain in recorded history. History
reads return five revisions per page. A source correction or original-file deletion
blocks new revisions; old values stay labeled as historical source claims. The
purchase date and system-recorded time remain separate. No asset ownership date
or current market value is inferred from these details.

`PurchaseDetails` owns the same validation for private HTTP
`/api/receipts/details/read`, `/api/receipts/details/save` and MCP
`receipt_details_get`, `receipt_details_save`. App-model tools cannot write or read
these new operations. Existing source-text recall can still quote the original note;
this release does not add typed claim aggregation or accounting reports.

Migration `0015_receipt_details` adds owner/receipt/source foreign keys, unique
request/revision identities, bounded integer cents/currency constraints and
immutable quote/date/reason history. It preserves old receipt reviews and snapshot
restore. No new dependency, live ingestion, provider call or installation restart.

## Purchase-detail suggestions (v0.21.0)

The purchase-detail reader offers exact USD line totals from the reviewed item’s own printed line and a uniquely labeled YYYY-MM-DD purchase date. Use source suggestions copies these into an editable draft; review and save explicitly. Ambiguous/multiple dates, invalid dates, other currencies, multiline item quotes and non-labeled prices remain unknown. No AI call, financial arithmetic or automatic write occurs. Current-source and original-file availability checks still apply.

## Explicit currencies (v0.22.0)

Purchase-detail review and suggestions now support USD, EUR, GBP, CAD, AUD and JPY
when the source prints the ISO currency code. JPY accepts whole yen; the other
supported currencies require exactly two decimal digits. Store exact integer
minor units, never convert currencies, round values, multiply totals by quantity,
or infer currency from a dollar symbol. Unsupported formats remain unknown.

Migration `0016_receipt_currencies` rebuilds the receipt-detail constraint while
preserving every historical revision, owner boundary, index and USD request
fingerprint. Old callers that omit currency retain USD behavior. Downgrade refuses
when non-USD revisions exist rather than deleting or converting history.


## Find purchases from an asset (v0.24.0)

Open **Assets**, choose an item and look under **Purchase records**. Each purchased
receipt line shows its latest optional recorded total/date, exact source passages,
recorded revision and this item's unit position within the line's full quantity.
Unknown or withdrawn values are not replaced by an old revision. Open the source
or **Open receipt and purchase history** to inspect/edit the original receipt.
After editing, use **Refresh purchase records** to reload the summary.

Reads follow current reconciliation decisions and physical-unit bindings. Moving
or dismissing a receipt association removes it from the former item; undo restores
it. The original receipt review still preserves its historical acceptance result.
Only confirmed purchased receipt lines qualify; single-item proposals, possession
statements and unrelated evidence remain in the existing sourced details view.
Missing optional details appear as unknown and can be added in the receipt editor.

A whole line total covers its full quantity. The same receipt total may therefore
appear on several physical units; never add these appearances together or interpret
them as individual unit prices. Separate receipts are not consolidated. A receipt
supports a past purchase and does not establish current ownership. Corrected notes
and deleted originals are explicitly historical; new edits remain blocked by the
shared purchase-detail source checks.

`AssetPurchases` supplies authenticated `GET /api/assets/{id}/purchases` and read-only
MCP `asset_purchases`. Both verify asset ownership and return at most five receipt
lines per page with an opaque receipt/line cursor. No model tool, write operation,
provider request, new dependency or schema change. Version 0.25.0 includes bounded latest purchase claims in named-asset Chat recall;
financial reports and automatic aggregation remain separate work.


Receipt duplicate checks also offer **Compare possible items** (v0.27.0): inspect
up to two candidate records and their exact identity/correction evidence before
choosing each physical unit. Inspection does not fill in or change your choices.
The bounded read-only comparison is shared with single-item and identity review.
