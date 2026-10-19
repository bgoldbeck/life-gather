# Verbose manual container release

Root-only bounded extension of the existing guarded release script. Add a Windows
double-click launcher, timestamped named stages and command start/elapsed output,
plain Docker build progress, health waiting status and sanitized completion/failure
messages. Preserve default-decline build/upload prompts, clean-main guards, local
size labels, stdin credentials, isolated smoke test and temporary-resource cleanup.
Do not print registry tokens or stdin data. Do not run a real build/upload for
this tooling change. No application version bump or migration.

Clash check: fetched main 4f10211 (v0.36.0, migration 0019); GitHub has only main
and no open PRs. Existing Publish-Container.ps1 and its offline command mocks are
the authoritative publisher. Original checkout has unrelated AUTH_REQUIREMENTS.md
and FIRST_TASK.md edits; leave them untouched. This clean worktree is reused.

Acceptance: observe missing logging/launcher tests fail, then exercise mocked
success/refusal/failure paths, parse both PowerShell scripts, check launcher arguments
and verify no token exposure or real Docker/network invocation. Add usage docs,
commit/push/PR/merge and delete the merged branch. Continue cross-source purchase
reconciliation on a new branch afterward. This early planning commit makes the
work visible before implementation, as requested.

Verified: missing launcher test failed before implementation. All nine mocked
publisher paths now pass, including dirty/main guards, declined operations, failed
build, both upload modes, named/timed logs, plain build output and no token leakage.
PowerShell parser passes and launcher arguments/exit handling are checked. No real
build, registry login/upload or running-container mutation. This is tooling only.
