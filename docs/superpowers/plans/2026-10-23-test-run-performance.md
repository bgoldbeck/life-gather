# Test-run performance implementation plan

> REQUIRED: superpowers:executing-plans. Execute sequentially in the root chat under the repository no-agent rule.

**Goal:** Preserve full release coverage/isolation while reducing Windows/Docker overhead and exposing progress.
**Architecture:** Explicit database fixtures plus a stdlib Docker runner and cached Linux test image, integrated into Publish-Container.ps1.
**Spec:** docs/superpowers/specs/2026-10-23-test-run-performance.md. User approved the preceding review recommendations; routine implementation choices require no additional approval.

## Constraints/review focus
- No production code, migration, dependency or application-version change.
- Separate PostgreSQL server per shard; no shared PID1 template namespace.
- Collect once, select whole files, prove complete/disjoint allocation and expected collection count.
- No skipped verification, shared mutable user fixtures, live providers or deployment.
- Preserve publisher refusal/auth/source/smoke checks. Never log database credentials.
- Preserve empty legacy/recovery database semantics and inherited app fixtures.
- A failed collection/shard or Ctrl+C must never report release success; cleanup is invocation-scoped.

## Task1: explicit database setup
- [x] Add a failing fixture regression proving pure tests need no PostgreSQL and service fixtures avoid the default database.
- [x] Make template initialization demand-driven; separate environment isolation from configured_database; opt API modules/shared app fixtures into the latter.
- [x] Verify pure tests without a server and representative HTTP/service/recovery/isolation tests; Ruff/strict typing.

## Task2: Linux shard runner and publisher
- [x] Write failing offline runner tests for allocation/counts, shard failure and cleanup; publisher gate regression.
- [x] Add dedicated test Dockerfile/ignore, collection/shard helper and bounded Docker orchestration. Add elapsed progress, logs/manifest and --durations=25.
- [x] Replace host pytest in the publisher; retain host static checks and downstream gates. Document standalone/targeted commands and output locations.
- [x] Run full suite once via the new runner, static/offline publisher tests; review final diff sequentially.
- [ ] Fetch/reconcile latest main, push/update PR, exact-head merge and own branch cleanup; refresh graph/HTML and report measured duration/limitations. No application image rebuild/publication for excluded tooling-only changes.
