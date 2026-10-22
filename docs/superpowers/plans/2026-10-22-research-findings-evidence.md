# Save web research findings as evidence on an item

Phase 2 item 5 follow-up in the [feature plan](../../FEATURE_PLAN.md): Chat web
research (v0.67.0) shows cited, dated sources that are kept only in the chat
turn. This increment lets the user explicitly save one cited source to an asset
as evidence, with its URL, title, page date, excerpts and research time, and
shows saved findings on the asset.

## Scope

- Migration `0034_research_findings`: owner-scoped `research_findings` table with
  a row-level security policy like every other owned table.
- Service: save one cited source from a completed research turn the user owns to
  one of their assets. The server copies the source from the stored turn; the
  browser never supplies URL, title, date or excerpts. Saving is idempotent per
  request and per asset/URL; removing a finding keeps the row with `removed_at`.
- HTTP: save, list per asset (consolidated members included), remove.
- UI: a "Save to <open asset>" button per cited source in a research reply (only
  when an asset is open), and a "Web research findings" section on the asset.
- Personal records format 5 includes findings; restore accepts formats 4 and 5.
  Recovery accepts the new migration.

Nothing is saved without the explicit button press. Findings stay labelled as
web results about a product model, not evidence of ownership, purchase or fit.

## Acceptance checks

- Service tests: save, replay, duplicate, foreign/pending/non-research turn,
  unknown URL, non-asset target, remove, consolidated listing.
- Account isolation suite covers the new table, routes and identifiers.
- Export/restore round trip keeps findings; format 4 archives still restore.
- Frontend tests: save button only with an open asset, saved state, asset list.
