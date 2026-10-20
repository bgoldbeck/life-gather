# Broader documents implementation plan

Execute sequentially in the root chat; no subagents. User authorized implementation
of this feature then dockable navigation, with standing source/container releases.
Spec: `../specs/2026-10-20-broader-document-support-design.md`.

Baseline: fetched main `2b46d39`, v0.55.1, migration 0024; two local design commits
are included intentionally. No open PRs. Remote historical branches and parked
worktrees are preserved. Current code has only PDF Documents; graph refreshed
before discovery (3494 nodes/14473 edges; known partial AssetsPanel AST coverage).

1. Add meaningful failing service/API/MCP/UI tests for all formats, source locations,
   spreadsheet selection, formulas, malformed containers, encoding, owner isolation,
   exact originals, deduplication and archive/recovery preservation.
2. Extend the existing bounded subprocess parser with local stdlib text/CSV and
   safely bounded OOXML extraction. Do not execute macros/formulas/links. Preserve
   raw cell text and cached-value distinction; allow explicit encoding/delimiter
   and worksheet/range preview selection. No external parser/model service.
3. Add migration 0025 for document format and extraction metadata, defaulting old
   rows to PDF; preserve old PDFs, source namespace and APIs. Generalize shared
   service/HTTP/MCP metadata, original download extension and archive MIME/extension.
   Keep reviewed text/correction/deletion behavior and authenticated ownership.
4. Extend Documents review with format metadata, warnings and bounded preview
   selection; use plain text rendering. Preserve existing review/drafts and failures.
5. Verify affected then full backend checks from backend and frontend checks from
   frontend, wheel/build, migration upgrade, real browser synthetic workflows and
   Linux original/recovery smoke. Review all consumers and final diff. Bump 0.56.0,
   changelog/docs/capability inventory; refresh graph and HTML after checks pass.
6. Fetch/check clashes again, commit/push, PR tested head, merge without bypassing
   protection, update clean main and remove only this merged branch. Build isolated
   linux/amd64 image, smoke/recover and publish immutable/latest via guarded script;
   verify remote digest/revision. Report sizes; never redeploy a running installation.

Next separate feature: four-edge resizable primary navigation, left default,
per-account browser preferences, keyboard/pointer controls, responsive reflow and
coexistence with the existing independently docked assistant. Plan from current main
after document release; do not implement Power Center during these two features.
