# Correction chronology review and fix

Baseline: GitHub main `ca021fb` / v0.38.0, including requested/scheduled email
purchase discovery and its existing migrations. Preserve those features and the
canonical cross-source purchase helper.

Review reproduced two recorded-time gaps in existing correction workflows:

1. Batch move/restore explanations can precede one or more changed decisions
   when the wall clock stalls or moves backward.
2. Individual reassociation/undo samples explanation and decision times separately,
   so a fact read at the explanation's timestamp can show the preceding state.

Bounded implementation: align new correction explanations, effects and audit
timestamps while preserving original episodes, current authorization, exact retry
identities, receipt units, purchase amounts and append-only reversal history.
Do not rewrite stored historical timestamps or add a migration. Release as a patch
above the current main version, after checking for overlaps again before merge.

Acceptance: first demonstrate failing stalled/backward-clock and separate-clock
tests; verify individual existing/new targets and undo, multi-source move/restore,
known-at fact reads, audit/source time, idempotent retries and snapshot replay.
Run full backend/frontend verification from their own directories, strict types,
lint/format and builds. Attempt the prescribed code-only graph refresh. Follow
the standing PR/merge/branch cleanup and verified Linux/GHCR release workflow;
never restart a running installation or invoke live mail/AI services.
