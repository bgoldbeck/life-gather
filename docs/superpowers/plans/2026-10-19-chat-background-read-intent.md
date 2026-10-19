# Keep background Chat reads within current user intent

Baseline: clean GitHub main `5d97869`, v0.40.0. No competing work at kickoff.

Review/fix the remaining independent-read gaps in Chat:

- An initial saved-note selection must not overwrite a later text/action draft or
  reopen a failed selection after conversation navigation. Abort that selection
  when the user changes composer/context intent.
- Refresh daily usage independently after a request is saved. A slow metadata
  request must not keep Chat busy, and its late error/count cannot replace a newer
  conversation/request's state. Cancel obsolete metadata work on request/context
  changes and unmount.
- Serialize conversation-list page reads, disable repeated paging and deduplicate
  appended IDs. Keep browsing/starting conversations available during that read;
  a late list error must not appear in another conversation's context.

First reproduce the gaps with delayed success/failure tests; verify current drafts,
saved turns, request IDs and loading states. Preserve existing photo/receipt review,
source guards and provider permissions. No domain/API/schema/dependency changes.
Run full relevant verification and synthetic browser/Linux checks, attempt graph
refresh, then release v0.40.1 through the standing PR/GHCR workflow. No live calls
or running-installation changes.
