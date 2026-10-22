# Memories library

Memories lists source episodes already saved in the authenticated user's workspace.
It is independent of conversation history: unsaved chat messages are not added to
this library. Save a memory preserves up to 4,000 original characters using the
same deterministic, idempotent service as Chat/MCP. It creates no inferred facts
or assets, reserves no AI usage and sends nothing to an external provider.

The default list shows current saved note versions, newest first. Include earlier
versions exposes preserved originals and intermediate corrections. Source-type
filters follow each note's original root: saved text notes, photo transcriptions,
reviewed PDF text, or other evidence (including sourced profiles/asset actions).
A current note version is not a statement of current world ownership or verification.

Search uses up to 12 literal words, ANDed through the owner-scoped word index (case and accents ignored);
there is no fuzzy/semantic inference or model call. Search of current notes does
not match text found only in superseded originals; opt into earlier versions to
find those. Pages contain up to 25 240-character excerpts, ordered by recorded time
and opaque ID so equal timestamps remain stable. Fetching a subsequent page uses
an owned source cursor; new later sources appear after refresh. Bounded filters
are applied before pagination. File BLOBs and credentials are never loaded into
this metadata query.

Open evidence uses the same private paged source reader as Chat and the graph.
Current editable notes support source-preserving corrections and history. Photo
transcriptions remain marked AI-generated/unverified; PDF text is marked reviewed
rather than an original user statement. Note corrections retain their original
file links. If an original was deleted, its derived source/history remains visible
with an explicit deletion notice and no download/preview. File deletion retains
its existing backup/recovery-page limits; this release adds no deletion mechanism.

HTTP: GET /api/memories lists the library; POST /api/memories captures SaveText.
Writes require current session, origin, CSRF and the existing 32 KiB body limit.
Repeated/conflicting request identities follow the same existing source-ingestion
rules. The browser freezes an uncertain capture and retries its exact request.
MCP: memory_library accepts the same typed query/type/history/cursor/page input;
source reads and manual writes remain existing memory_source/memory_save_text tools.
No app model receives a new write tool. All queries and provenance are owner-scoped.

Asset evidence now shares this evidence component, fixing lost photo/PDF context
and deletion warnings. The heading's flex layout no longer affects image sections,
preventing horizontal overflow. New list/source reads reject stale responses after
search/navigation, and the list refreshes after correction.

No migration or dependency change. Verification includes current/history search,
root categories after correction/deletion, owner/CSRF/MCP boundaries, equal-time
pagination, concurrent capture replay, original snapshot restore, UI retry/correction
and race handling, and synthetic browser capture/provenance checks. No personal
records or paid/live provider calls are used. Graphify is unavailable in this host's
command path and standard tool locations; graph/HTML refresh could not run.
