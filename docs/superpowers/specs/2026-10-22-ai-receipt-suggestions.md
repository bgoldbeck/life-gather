# AI purchase-detail suggestions for receipts

Phase 2, increment 2 of [the feature plan](../../FEATURE_PLAN.md): "Add AI
price/currency/date suggestions to receipt intake using exact-money services,
source quotes and ambiguity handling."

## Scope

- On an accepted receipt's purchased line, **Suggest with AI** sends only that
  receipt's current saved text and the reviewed item quote to the user's selected
  AI connection (explicit external-AI permission, shared daily limit).
- The model returns a line total, currency, purchase date and the exact source
  passage for each, plus ambiguity notes. It has no tools and cannot write.
- The server grounds every suggestion deterministically before showing it:
  each passage must occur exactly in the source, the money passage must contain
  the item quote, the amount must be printed in its passage, and the date must
  be one reading of a printed date. Ungrounded values are dropped and reported.
- Ambiguities are flagged instead of guessed: a bare `$`, missing currency,
  numeric dates readable as month/day or day/month, several distinct amounts
  or dates, and dates labelled as delivery/shipping/return.
- Suggestions fill an editable draft only. Saving stays an explicit human
  revision through the existing exact-money service, with a new `reviewed`
  basis that accepts printed amounts/dates (e.g. `$349.00`, `10/18/2026`) once
  a person confirms currency and date reading. The existing strict `labeled`
  rule and its request fingerprints are unchanged.
- Migration adds `receipt_details.basis` (`labeled` default, `reviewed`), so
  each revision records whether it came from labelled text or a reviewed
  interpretation.

## Out of scope

Totals/taxes/allocation, currency conversion, unit prices, automatic saves,
new currencies, OCR changes and MCP access for app models.

## Acceptance checks

- Grounding unit tests: exact passages, printed amounts with symbols, thousands
  separators and decimal commas, ambiguous dates, conflicting currencies,
  injected/ungrounded model output.
- Service/route tests with a synthetic provider: permission off, other user's
  receipt, usage recorded, source changed, reviewed save accepted, labeled
  rules unchanged, migration upgrade/downgrade.
- UI test: request suggestions, see ambiguity warnings, copy into draft, save
  with reviewed basis.
