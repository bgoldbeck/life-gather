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
