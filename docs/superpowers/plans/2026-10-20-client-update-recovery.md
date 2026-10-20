# Prevent stale browser UI after deployment

Claimed on `codex/client-update-recovery`, baseline main `2229dc1` / v0.58.0 /
migration 0025. Clean checkout, no open PRs or unmerged remote work overlaps.

## Evidence and cause

The running v0.58.0 image serves Power Center and navigation docking correctly.
The user confirmed a hard refresh restores both. The startup HTML has no explicit
cache policy, and AuthGate independently refreshes server build metadata every
minute/on focus without replacing the executing JavaScript. An old tab can
therefore claim the new server version while running old UI code.

## Bounded fix and acceptance

- Revalidate startup HTML and other non-hashed static responses; cache only
  successful Vite content-hashed assets immutably. Preserve API no-store and
  private data/static boundaries, including conditional responses and errors.
- Compile UI build metadata from the single backend version source and the
  existing Docker APP_REVISION argument. Never maintain a second version string.
- Pin displayed UI build to the executing bundle. Compare authenticated/anonymous
  session checks with it; show an accessible update notice on mismatch with an
  ordinary Reload action and unsaved-draft explanation. Never reload automatically,
  erase drafts, change permissions or restart the running installation.
- Tests reproduce stale version/docking behavior at the build boundary, verify
  version/revision changes, missing metadata and unchanged builds, safe reload
  affordance, and draft preservation. HTTP tests cover HTML/304/hash-assets/error
  cache policy. Verify actual built metadata and synthetic browser behavior.
- Release patch 0.58.1 after backend/frontend checks and source graph/HTML refresh.
  Commit/push, PR/merge/tested-head checks, merged branch cleanup, clean-main
  linux/amd64 build, isolated smoke, GHCR SHA/latest publication and remote digest/
  revision verification follow existing authorization. No schema/dependency change.
