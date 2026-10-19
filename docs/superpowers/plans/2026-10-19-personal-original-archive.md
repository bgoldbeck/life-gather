# Personal records and original-file archive

Baseline checked October 19, 2026: main 40381490db84fb9f0a7f0db2394dc0fd78edbad4, v0.51.0, migration 0023. Clean single checkout, remote feature branches and open PRs checked; no competing archive implementation. Previous source and image passed 552 backend / 244 frontend tests, quality/build checks and actual-image recovery smoke. This early scope is published before implementation.

The personal JSON download includes file metadata but requires downloading original photos/PDFs individually. Add an explicit owner-only ZIP download containing the same frozen records.json plus active saved originals and a versioned manifest with record IDs, fixed safe paths, lengths and SHA-256 hashes. Keep all-user encrypted installation recovery separate; this personal archive excludes authentication, credentials, settings, connector/job state and processing caches, and cannot restore an app.

Reuse one SQLite read transaction for both record JSON and binary reads. Refactor a connection-owned RecordExport rendering helper while preserving download(actor), format 2 and existing 10,000-row/16 MiB JSON bounds. Stream BLOBs in chunks on the same native SQLite connection, verify size/hash, include only the current owner's nondeleted originals, and refuse missing active/corrupt data. Never reconstruct deleted originals from previews/caches/history.

Use standard-library ZIP_STORED with a strict 64 MiB total output bound including headers, manifest and central directory, and at most 1,000 originals. Fixed UUID-based member paths and conservative extensions; original user filenames remain JSON data. No archive traversal/links, no filesystem/database backup payload and no partial HTTP file. No schema/dependency change, import, deletion or automated provider action.

Thin authenticated POST /api/export/archive reuses session/CSRF and no-store/nosniff/attachment controls. Settings offers an explicit Include originals (ZIP) choice, defaulting to existing JSON. Preserve busy/duplicate prevention, abort/late-response handling, safe filename and object-URL cleanup; validate MIME/size/ZIP signature. Explain scope and limits clearly without suggesting sharing an all-user backup with an individual user.

Acceptance: two-owner records/photos/PDF fixture including exact money, separate units, custom fields and correction history; byte/hash/manifest equality and private credentials absent; deleted originals excluded; one-snapshot concurrent commit race; safe names and file/row/byte limits including ZIP closing overhead; failures release the transaction and return no partial file; only read operations. HTTP session/CSRF/privacy controls, UI opt-in/default JSON, busy/failure/abort/late/filename/MIME checks, and real synthetic browser ZIP download inspected for actual contents at desktop and narrow width. Run full appropriate quality/tests/builds, refresh code graph/HTML, repeat final clash checks and complete standing source/image release sequence. No agents, live data/providers or existing-installation deployment. Target v0.52.0 unless main advances.

Source acceptance: 568 backend / 253 frontend tests pass, as do backend Ruff and
strict mypy (226 files), frontend formatting/lint/types and production build.
Actual browser download: valid 13,596-byte ZIP, 27 records and two originals with
matching lengths/SHA-256, including custom detail correction history. AI consent
remains unchanged; 390px page has no horizontal overflow. Linux mounted-source
archive plus 42.9 MB encrypted installation recovery smoke passes with no network,
read-only root and non-root user. No source or registry release claimed by these
checks. Wheel includes the archive service; graph/HTML refreshed (3,210 nodes /
13,921 edges). Fresh refs/open PRs show no overlap, main remains 4038149 and
migration remains 0023. Clean-main image verification follows source acceptance.
