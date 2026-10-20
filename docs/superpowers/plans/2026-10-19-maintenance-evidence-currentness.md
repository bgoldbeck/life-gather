# Maintenance evidence currentness — v0.55.1

Baseline: clean main `83b4a7a`, v0.55.0, migration `0024_maintenance`.
Fresh fetch found no other feature branches, worktrees, open PRs or issues.
Graph relationship lookup and actual source confirm that generic chat recall
follows note corrections but does not identify typed maintenance revisions.
An old completed-only phrase can therefore retrieve an obsolete task statement
after reopening. Maintenance itself already stores the correct current head.

## Scope

Add one owner-scoped, read-only service projection from an actual maintenance
revision source FK. Preserve the queried revision's fields and original linked
entity, describe its current canonical target, and identify the current revision
and source separately. Namespace text alone grants no typed authority. Read the
revision and head in a single SQLite snapshot; refuse ambiguous associations.

Expose the same metadata in chat evidence, source HTTP and private MCP source
reads. Follow the current source when keyword/AI recall matches an earlier
revision. Retain eight-source and byte limits, prefer current evidence to old
history, and retain explicit historical markers if later evidence is omitted.
Teach the answer instruction to use typed current fields for tracked tasks,
preserve unknown dates, and never substitute old completion text for missing
current evidence. Keep provider schemas, consent, budgets and write tools intact.

In the existing evidence viewer label current versus earlier maintenance
statements and provide an explicit View current maintenance statement action.
Keep the original text visible. Source inspection remains usable without AI.

No migration, new dependencies, task parser, scheduling, inferred interval,
external provider call, live ingestion or deployment is included. This is a
correction to v0.55.0 recall, so use patch version 0.55.1.

## Acceptance

- First reproduce the missing historical marker/current source in a regression.
- Cover open, completed, canceled and reopened revisions; unknown dates; owner
  isolation, forged namespace sources, bounded recall and immutable originals.
- Verify the HTTP/MCP projections agree and foreign source reads fail without
  leaking metadata. A fake provider must receive current typed fields and valid
  source IDs even when only an obsolete phrase matches search.
- UI tests cover historical/current labels, disabled loading state and explicit
  navigation without rewriting evidence. Inspect the real synthetic browser at
  desktop and 390px, including keyboard access and light/dark appearance.
- Run full backend/frontend tests, strict typing, lint/format, wheel/frontend
  builds, source-only Linux recovery, then refresh local code-only graph/HTML.
- Review scope, repeat clash check, release tested source through PR/merge and
  merged-branch cleanup; clean-main Linux build, isolated smoke, GHCR immutable
  and latest publication, fresh-image recovery and remote digest/label checks.

This kickoff commit precedes implementation. Final acceptance is recorded below
only after verification.
