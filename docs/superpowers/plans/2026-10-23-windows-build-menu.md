# Windows build terminal menu

Goal: double-click a Windows command file on a fresh Git clone and see setup,
verification, local build and publishing actions without installing developer runtimes.
User selected the terminal menu instead of a native GUI. Work stays in this chat.

Approach: Windows PowerShell 5.1 provides the menu, status table, elapsed stages
and explicit setup actions. Git and Docker Desktop are host requirements; GitHub
CLI and browser authorization are required only for publication. Offer winget
installation with visible progress; fall back to official download pages. Never
silently install software, enable WSL, restart Windows or start the app.

- [ ] Add `scripts/Container-Helper.ps1` and `.cmd`: refreshable status, numbered
  setup and release actions, readable errors, return to menu after completion.
  Preserve existing direct publisher arguments and combined preview launcher.
- [ ] Remove publisher host uv/npm requirements: run the existing Linux test
  orchestrator in a Python/Docker-CLI controller with a read-only source mount,
  writable isolated report directory and local Linux engine socket. Run strict
  backend checks in the existing backend test image and frontend verification
  in a cached, allowlisted Node verification image. Fail closed on every check.
- [ ] Add offline behavior tests for dependency states, setup failure, menu
  routing, canceled/invalid selection, missing authentication, failed verification
  and preservation of build/upload gates. Verify real container verification on
  Windows and preserve ignored logs. No skipped test suites to simplify builds.
- [ ] Document fresh-clone usage, Docker/WSL/restart boundaries, authentication,
  image/cache downloads, controller socket access and remaining recovery steps.
  Tooling-only: no app version/schema/runtime image changes.
- [ ] Run relevant PowerShell and runner regressions; review final diff, refresh
  Graphify/HTML, fetch/clash-check again, commit/push, PR and merge after checks.
  No application image publication is needed for excluded release tooling alone.

Baseline: clean local main fast-forwarded from 1f225ad to 9a97027. PR #142 already
provides Linux sharded backend tests; reuse it. Open PR #139 operations work changes
application/docs/migration 0038, with no release-script overlap. Keep it untouched.
