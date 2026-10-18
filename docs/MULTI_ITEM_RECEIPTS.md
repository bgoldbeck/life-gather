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
