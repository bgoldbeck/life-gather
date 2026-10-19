# Clarify refused manual releases

The user's screenshot showed a correct dirty-checkout refusal followed by an
ambiguous session-completed footer. Keep the refusal; show explicit final outcomes:
FAILED, CHECKS PASSED, BUILD DEFERRED, BUILT (no upload), UPLOAD DEFERRED or PUBLISHED.
Print only uncommitted file paths, never their contents, so the user can understand
what needs deliberate committing/stashing. Preserve exit codes, prompts and all
release guards; do not automatically stash, commit or remove local edits.

Clash preflight: main 6abf92d (v0.37.0, migration0020), no open PRs or competing
release branches. Extend the publisher merged in PR53, not a second script. User's
two unrelated main documentation edits remain untouched. Tooling-only change; no
application version bump, schema change, real build/upload or deployment.

Acceptance: strengthen offline mocks to capture failure-path information records;
observe missing result markers fail, then check all nine existing paths plus dirty
file names, exit preservation and token redaction. Parse PowerShell and retain the
double-click launcher. Commit/push/PR/merge/cleanup after tests; early scope push first.

Verified: the strengthened dirty-refusal result test failed before implementation.
All nine mocked publisher paths now pass with explicit outcomes, dirty path output,
parser/launcher checks, correct stop/publish counts and token redaction. Final clash
check retains main 6abf92d with no competing PR. No real release or local edit mutation.
