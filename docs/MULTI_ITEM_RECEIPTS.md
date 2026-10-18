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
- Drafts persist in Review → Receipts. The source links back to the receipt review.
  Single-item and receipt reviews cannot accept the same source twice. A rejected
  draft stays in history; use a corrected note version to propose revised content.
- Corrections retain the original source, stale the draft and prevent acceptance.
  Original photo/PDF deletion also prevents acceptance. Rejection remains possible.
  Accepted facts retain source evidence, and photo attachments follow each unit.

This increment does not extract prices, currencies, purchase dates, totals, taxes,
refunds, warranties or accounting entries. Those typed financial/date records are
later roadmap work; no monetary values are stored as free-form accounting facts.
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
