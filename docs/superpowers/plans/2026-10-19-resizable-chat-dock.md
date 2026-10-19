# Right-default resizable assistant

Scope: reuse the persistent ChatDock, default to the right for accounts without
a saved position, and add a visible pointer/keyboard resize divider. Preserve
existing saved positions, drafts, collapse and navigation behavior. Save separate
width and height preferences per account; older preferences remain readable.
Keep the narrow-screen bottom layout, with a vertical resize interaction there.
Bound sizes so page and assistant remain usable; no backend data/schema change.

Acceptance: component interaction tests cover defaults, legacy preferences,
all docking directions, pointer and keyboard resizing, bounded sizes,
collapse/expand, persistence/account isolation and narrow-screen orientation.
Run frontend suite/lint/types/format/build and backend verification for release;
refresh the local source graph and HTML after checks. Release v0.49.0 through
the authorized commit/push/PR/merge and isolated Docker smoke/GHCR sequence.
