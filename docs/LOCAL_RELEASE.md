# Local container release

Run `scripts/Publish-Container.ps1` from PowerShell on a machine with Git, uv/Python 3.13, Node/npm, and Docker's Linux engine. Publishing also needs GitHub CLI authenticated as a maintainer with `write:packages` permission. It uses local checks and GitHub Container Registry, not hosted GitHub Actions or a paid runner.

The image uploads to GHCR, not into the Git repository. The script never commits/pushes source, opens/merges PRs, changes package visibility, or restarts your app/TrueNAS. Commit or safely stash outstanding changes first. To update `latest`, separately push/merge the intended source to GitHub `main`, then use a clean local `main` at that same commit. Do not include unrelated edits just to satisfy this preflight.

## Feature-completion policy

The user's 2026-10-18 standing instruction in `AGENTS.md` is: after a scoped feature
passes its required checks, commit, push, open a PR, merge the tested head, delete
the merged feature branch, then build/smoke-test clean GitHub-matching `main` and
publish its commit tag plus `ghcr.io/bgoldbeck/life-gather:latest`. This sequence is
authorized without repeated confirmation for each feature. Preserve branch checks,
owner isolation, size reporting, and the script's release guards. The agent may
answer the existing build/upload prompts using this standing authorization.
Other interactive/manual invocations still retain their default decline behavior.
Hosted GitHub Actions stays disabled; publication does not redeploy TrueNAS.

## Commands

Check the source only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-Container.ps1 -CheckOnly
```

Build and test locally without uploading:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-Container.ps1
```

Build, test, and publish the commit tag and TrueNAS `latest`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-Container.ps1 -Publish -PublishLatest
```

Use `-Publish` alone to publish only `sha-<full-commit>`, leaving `latest` unchanged. The command-line execution policy applies to this one PowerShell process; it does not modify machine/user policy. Review the script before running it. PowerShell 7 users can invoke it with `pwsh -NoProfile -File` instead.

## Bandwidth and prompts

The script reads locally available image sizes without pulling. It runs backend/frontend checks and validates both Compose configurations. Dependency setup (`uv sync`/`npm ci`) may download missing packages, so choose a suitable time even for check-only runs.

Before building, it asks `Build the Linux image now? [y/N]`. Docker can download missing base layers. After a successful build and isolated container smoke test, it reports the resulting local image sizes. If publishing was requested, it separately asks `Upload ... now? [y/N]`. Entering anything other than `y` or `yes` declines that operation. There is no unattended/automatic approval switch.

Docker's image-list and inspect sizes are labeled as local engine measurements, not exact compressed transfer sizes. Actual upload depends on missing registry layers and cannot be promised from those numbers. No image is downloaded just to measure it. An upload failure can leave already-transferred layers or a successfully published commit tag; rerunning may reuse them. `latest` is updated only after the commit-tag push succeeds.

## Checks, credentials, and cleanup

- Any failed native command stops the release. Dirty source or a moved GitHub main prevents publishing `latest`.
- Builds target `linux/amd64` and include source/revision labels. The script uses the existing Docker context; it does not install runtimes or switch engines.
- Smoke tests run a uniquely named container without host ports or your real volumes, using temporary private storage. They check health, homepage, icon, anonymous auth setup, initial auth database migration, non-root UID, absence of Node at runtime, and writable private data. The container is removed even after a failure. An unremovable container produces a warning naming it.
- GitHub's token is piped to Docker over stdin, not placed in command arguments or printed. Docker login uses a temporary per-run config that is removed at the end. No token is committed to source or retained in the user's Docker config by this script.
- On first publication, maintainers must separately verify public package visibility. The existing LifeGather package is already public; this script does not change it.
- Pull/redeploy on TrueNAS afterward. For the port change, use the newly published image and `8787:8787` mapping together; old preview images still listen on container port 8000. New Google-login builds need the OAuth settings in [GOOGLE_LOGIN.md](GOOGLE_LOGIN.md).

Offline publisher tests run without Docker/network/registry operations:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tests\Publish-Container.Tests.ps1
```

The script was syntax-checked and exercised with mocked commands for nine success/refusal/failure paths. A real build/push has not been run for this script; do not mistake offline tests for verified registry publication.
