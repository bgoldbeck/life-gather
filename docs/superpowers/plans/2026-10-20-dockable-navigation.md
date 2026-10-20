# Dockable primary navigation implementation plan

Execute inline in the root chat; no agents. This is the second feature explicitly
requested after broader documents. Spec: `../specs/2026-10-20-power-center-design.md`,
primary navigation section only. Power Center itself remains a later feature.

Baseline: current clean main `d55c72e`, v0.56.0, migration 0025, PR82 merged; no open
PRs or competing navigation work. Historical remote branches/parked worktrees are
preserved. Documents image is already built and smoke/recovery verified; its upload
may continue while this feature is implemented, but main must not advance until
both document image tags/digest/revision have been verified. Graph lookup connects
Workspace, ChatDock, saved layout and their current tests; inspected source agrees.

1. Add failing Workspace integration tests for missing navigation dock controls,
   every edge's pointer/keyboard resizing, independent account preferences, reset,
   invalid/unavailable storage, narrow fallback and preservation of page/chat drafts.
2. Add focused NavigationDock component and CSS. Keep the same mounted page and
   assistant while CSS grid areas reorder navigation. Default left, four edges,
   bounded separate width/height in per-account browser layout storage; no messages,
   credentials or backend settings in that storage. Pointer capture/cancel and
   accessible separators, arrows/Home/End and position selector must work.
3. Wrap existing navigation/page in App; retain all destinations and skip-to-content.
   Horizontal docks reflow labels and scroll within the navigation panel when needed.
   At narrow widths use compact top navigation without rewriting desktop preference;
   clamp viewport changes, preserve readable content, and nest the unchanged assistant
   independently so choosing the same edge does not overlay either panel.
4. Verify full frontend interactions/types/lint/format/build, relevant backend version
   checks and wheel, actual browser every edge/keyboard/pointer, Light/Dark, narrow
   and account/reset/reload/draft behavior. Review layout/storage/async boundaries.
   Version 0.57.0, changelog, user docs/capability inventory and graph/HTML refresh.
5. Repeat fetched refs/open-PR/version/migration/consumer clash checks; commit/push,
   create PR, verify exact tested head/mergeability, merge without bypass, update
   clean main and delete only this merged branch. Run guarded local image release,
   isolated actual-image recovery and remote immutable/latest digest/revision checks.
   Standing publication authorization applies; no live-app redeployment.
