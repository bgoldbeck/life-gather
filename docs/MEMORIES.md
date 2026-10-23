# Memories library

## What memories are

A memory is a piece of evidence saved in its original words: a note you saved,
text read from a photo, reviewed document text, email evidence from a scan, or the
record LifeGather keeps when you add or change an asset. A memory says what a
source said; it is not a checked fact. Facts, assets and purchases point back to
the memories they came from so every detail can be traced.

The assistant uses memories in two ways. **Ask AI** searches them by keyword and
answers only from the matches, with a button for each memory it cites. The
**AI assistant** links each detail it saves to the memory it came from. Memory
text is sent to an AI provider only when you enabled external AI access and chose
an AI mode; saving and searching stay on your server.

## Deleting memories (v0.84.0)

Each memory in the list has **Delete**. Confirming removes the memory's saved text
for good; it cannot be undone or restored in the app.

- The text is replaced by a short deletion notice, the memory leaves this list,
  search, global search and Ask AI recall, and short quotes from it in fact
  evidence are cleared. A content-free `source_deleted` audit receipt is written.
- Deleting a saved note deletes every version of it (the original and all
  corrections), so an older version cannot reappear.
- Assets, facts, purchases, receipts and proposals already saved from the memory
  stay, and opening their evidence says the memory was deleted. Change or delete
  those separately. Purchase evidence keeps its own exact quotes.
- Deleting the memory of a photo or document does not delete the file or its
  stored extraction; delete the photo or document on its own page for that.
- To remove a whole Gmail connection or scan together with the assets, facts
  and purchases made from it, use [source erasure](SOURCE_ERASURE.md) (v0.99.0).
- Re-running a scan or saving the same import again does not bring the text back.
  Saving a new note with the same words creates a new memory.
- `POST /api/memories/delete-many` with `{"memories": [{"source_id"}, ...]}`
  (1 to 25 unique items, all or nothing) needs the private session and CSRF.
  Repeating it for deleted memories succeeds without new receipts. No MCP or
  model deletion tool is added, and no migration: the deletion is recorded by the
  audit receipt, which exports and restores with the records.

If the deletion reply is interrupted, the app cannot confirm the outcome. Use
**Refresh memories** to check the current list, or explicitly retry; repeated
deletion of the same source is safe.

## Browsing

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
its existing backup/recovery-page limits. Memories themselves can be deleted
since v0.84.0 (above).

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
