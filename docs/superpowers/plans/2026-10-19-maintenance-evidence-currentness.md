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

## Verified source acceptance

The old-only completion keyword regression first failed against v0.55.0. The
final implementation preserves old fields and follows the reopened source with
unknown dates. Seven maintenance recall cases cover three states, owners,
namespace spoofing, small byte budgets, eight-source limits, HTTP/MCP agreement,
fake-provider citations and exact Chat replay. Existing identity tests also check
original/canonical source targets through consolidation and reversal. Follow-up
reads are capped at eight even if concurrent edits keep advancing a head.

Final full backend: **623 passed in 467.97s**. An earlier direct pytest run had
one installed-metadata mismatch after the patch bump; refreshing the editable
package with locked uv sync resolved it before the final clean full rerun.
Frontend: **287 passed across 51 files**, plus TypeScript, lint, format and Vite.
Ruff/format and strict mypy pass for 241 files including the recovery script.
The v0.55.1 wheel was built and inspected for version and bounded recall code.

Actual synthetic browser inspection verified historical/current sources,
keyboard current-statement navigation, preserved originals, unknown completion,
reload and current-first keyword results without AI. Desktop and 390px light/dark
layouts pass without page overflow; original appearance/dock/viewport were
restored and the temporary tab/server closed. Source-only Linux recovery passed
with a 42,934,272-byte database, original statements, current task heads and two
owner boundaries. Fresh release-image verification follows clean-main merge.

Final code-only Graphify extraction and HTML refresh: 3,454 nodes / 14,803 edges,
one worker, no model calls. A repeated fetch found main unchanged at `83b4a7a`,
with no competing PRs or migration/version collisions. No source schema,
dependency, provider access, model write permission or deployment change.
