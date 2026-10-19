# Complete bounded current-record comparison

Baseline: current GitHub main `057632d`, v0.38.1, migration head
`0021_email_discovery`; no competing branches or open PRs at kickoff.

Deliver a read-only comparison of two explicitly selected, existing private asset
records. This is the next duplicate-resolution inspection increment, not a merge
implementation or permission to perform a later merge.

Domain service: use one SQLite read snapshot, owner validation and bounded
collections for current statement versions with evidence, incoming relationships,
aliases, photo-link metadata (including deleted originals), current discovery/unit
associations, receipt line claims and cross-source purchase evidence. Show original
IDs, source links, recorded/world times, unknowns and inferred inventory status.
Preserve exact amounts and whole-line/order scope; do not calculate totals.

Flag overlapping differing statements, replacement links and distinct units of the
same discovery/purchase line. These are inspection warnings, never automatic
identity decisions. Show explicit section limits and refuse a complete result if
any collection or UTF-8 response budget exceeds its bound. Historical versions
remain on their original records and are outside this current-version comparison.

Expose the same read through authenticated HTTP/MCP and an optional Assets panel.
Require a deliberate second-record choice; preserve close/navigation intent when
requests finish late. No model invocation, graph writes, audit/source writes,
schema migration, dependency or new provider permission.

Acceptance: two-user isolation and unsupported/same-record refusal, snapshot
consistency/read-only counts, literal/status/date conflicts, incoming references,
photo reuse/deletion, receipt quantity/currency preservation, section/byte overflow,
HTTP/MCP parity and UI selection/error/navigation/source inspection tests. Verify
full backend/frontend checks and synthetic browser/Linux smoke. Publish v0.39.0
through the standing commit/PR/merge/branch cleanup and GHCR workflow; no redeploy.

Verified: 410 backend / 145 frontend tests pass, including twenty new backend and
seven UI cases. Lint, format, strict mypy, TypeScript, Vite and package builds pass.
Concurrent alias insertion proves sections share a committed snapshot. Source
correction, immutable snapshots, distinct units, replacement links, unknowns,
overlapping dates, large integer display, exact JPY/USD amounts and every collection
cap are covered. An AST comparison confirmed that sharing the receipt read body
introduced no semantic change to its existing public read behavior.

Browser QA exercised explicit selection, conflict/source inspection, photo reuse,
whole-line USD 49.90 and 390px stacking. Fixed an existing photo-upload grid
minimum width discovered during that check; document width is 375px at a 390px
viewport, with no overflowing main elements. Temporary viewport was reset and
preview tab/server closed. Synthetic Linux smoke covers comparison, corrected
sources, exact JPY claims, private refusal and snapshot restore. Graphify is not
installed; code graph/HTML refresh could not run. No live provider call or migration.
