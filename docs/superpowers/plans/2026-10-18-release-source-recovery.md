# Safe release-script prerequisite recovery

Approved behavior: automatically fetch GitHub main, fast-forward a clean local main
when it is behind, reload the updated release script, then verify/build normally.
Never stash, discard, reset, merge feature branches or overwrite diverged/local-only
commits. Feature/detached checkouts remain usable for deliberate commit builds;
publishing latest still requires clean main matching GitHub exactly.

Implementation:
- Add a small source preflight helper before the publisher loads its implementation.
  Validate the expected origin, refresh stale index metadata, reject actual dirty
  paths, fetch main explicitly, inspect ancestry and fast-forward only behind main.
  A single restart reloads any updated script and version; a second concurrent main
  advance stops instead of looping. Capture release metadata after source recovery.
- Offer an explicit -RepairAuthentication option to start GitHub login or request
  write:packages when needed. Browser authorization stays with the user. Without the
  flag, explain the exact repair command and stop before expensive work. Missing
  tools, network failures and Git conflicts remain clear, actionable stops.
- Extend offline publisher tests and add real temporary Git repository tests for
  behind/up-to-date/ahead/diverged/dirty/detached/feature states and fetch failures.
  Prove an updated script is reloaded once and release flags survive the restart.
- Update local release documentation; preserve prompt-free explicit -Publish.
  Commit/push/PR/merge/clean up after verification. This changes host release tooling
  only: no runtime/version/schema change and no Docker rebuild/upload needed.

Baseline: origin/main 916d178, newer chat/photo changes are already merged and do
not touch release scripts. No open PR or overlapping script work at kickoff.
