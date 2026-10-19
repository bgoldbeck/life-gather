# Close successful Windows helpers

Baseline main e32a6bc, application v0.45.0. No open PRs or overlapping script
branches at kickoff. Preserve the unrelated private-record-export branch.

User request: both Windows helper scripts should exit automatically on success.
The current `.cmd` wrappers pause unconditionally. Direct PowerShell invocation
already exits normally. Update only the two wrappers, leaving the PowerShell
operations, return codes and data protection intact. Failed invocations should
still print a helpful message and pause for inspection. Use `exit /b`, preserving
an existing caller terminal instead of forcibly closing it.

Verify both wrappers in actual cmd.exe using a substituted inert child command:
success must never wait for input; failure must pause and preserve its nonzero
status. No Docker, credentials or publishing calls in these tests. Run the
existing offline launcher/publisher/source-recovery tests under PowerShell 5/7,
refresh the local code graph, then commit/push/PR/merge/close this branch.

The v0.45.0 image publication already in flight targets e32a6bc. Do not merge
this script-only change until that publisher finishes its main-tip check.
No application version bump, schema change or new Docker rebuild is needed for
this launcher-only fix.

Verified: the new cmd.exe fixture test first reproduced the successful publisher
waiting for keyboard input. Both launchers now pass actual success/failure input
and exit-code checks under PowerShell 5.1 and 7. Existing publisher (24), test-login
(5) and source-recovery (15) scenarios pass in both shells. No application code,
data, migration, deployment configuration or authentication change.
