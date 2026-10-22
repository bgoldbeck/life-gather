# Search and navigation between records, sources and photos

Phase 2, item 4 of [FEATURE_PLAN.md](../../FEATURE_PLAN.md): improve retrieval and
source/photo navigation where representative tasks show friction.

## Friction

- Finding something means guessing which page holds it. Memories searches
  sources only, Assets filters assets only, Photos and Documents have no search.
- A photo opened in Photos does not show which assets it is attached to, so you
  cannot get from the picture back to the item.
- Other pages cannot open a specific photo, document or source; they can only
  switch pages.

## Scope

1. **Find anything** (`GET /api/search?q=`): one owner-scoped, bounded search over
   assets and other graph records (by name), photos (by filename), documents (by
   filename and reviewed text) and current source text. Portable SQL only
   (case-insensitive `LIKE` with escaped wildcards, all words must match), so it
   runs unchanged on SQLite and on the planned PostgreSQL storage; no new index,
   table or migration. Merged duplicate assets appear once, under the surviving
   record. Superseded note revisions and deleted photos/documents are excluded.
   A source that belongs to a photo or document says so and opens that original.
2. **Search box in the top bar** with grouped results (keyboard and screen-reader
   accessible). Choosing a result opens it: assets in Assets, other records in
   Graph, photos in Photos, documents in Documents, other sources in Memories.
3. **Open a specific record**: Photos, Documents and Memories accept an initial
   photo/document/source to open.
4. **Photo to asset**: a photo's detail lists the assets it is attached to with an
   Open button.

## Acceptance checks

- Service tests: matches across kinds, all-words matching, wildcard characters are
  literal, owner isolation, merged assets collapse, superseded notes and deleted
  photos are hidden, per-kind limits, input bounds.
- HTTP test: requires a session; returns the same results.
- UI tests: searching shows grouped results and choosing each kind navigates to
  the right page with that record open; photo detail opens a linked asset.
- Backend `pytest`, `ruff`, `mypy`; frontend `vitest`, `eslint`, `tsc`, build.

## Out of scope

Ranking/relevance scoring, semantic or vector search, OCR or new formats, MCP
changes (the assistant already has `memory_search`), maintenance and purchase
records in global search.
