# Saved-note correction and history

Deliver the next text-memory increment over the shipped chat. Explicit user
corrections append an immutable original-text source and a version link; they
never overwrite evidence or change inventory/graph facts. Existing notes need no
backfill. Migration 0007 adds owner-constrained note revision links, request replay
keys, and one successor per version. One serialized transaction commits source,
search entry, revision, and audit together. Stale-version edits conflict, and
identical request retries return the same revision even after later corrections.

Default source search filters superseded note versions before applying limits.
The old evidence remains directly inspectable, including saved conversation
citations; the source panel marks it historical and links to the current note.
History is paginated, private, and accessible without AI. Correcting a note does
not correct graph facts derived from that source. Do not expose correction tools
to the conversational model; HTTP and typed MCP adapters share the note service.

Implement sequentially with no agents. Verify atomic rollback, concurrent edits
and replays, stale conflicts, unknown/foreign IDs, CSRF, original-text retention,
search after many revisions, source history paging, upgrade preservation, export,
restart/snapshot restore, safe UI rendering, and retry/conflict interaction.
Run the full existing checks and inspect the UI with synthetic data. Graphify is
unavailable here; use source/tests and report that limitation. Release through the
standing commit/push/PR/merge/branch-cleanup/local-build/GHCR publication rule.
