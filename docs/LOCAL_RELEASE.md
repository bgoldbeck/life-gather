# Local container release

Run `scripts/Publish-Container.ps1` from PowerShell on a machine with Git, uv/Python 3.13, Node/npm, and Docker's Linux engine. Publishing also needs GitHub CLI authenticated as a maintainer with `write:packages` permission. It uses local checks and GitHub Container Registry, not hosted GitHub Actions or a paid runner.

The image uploads to GHCR, not into the Git repository. The script never commits/pushes source, opens/merges PRs, changes package visibility, or restarts your app/TrueNAS. Commit or safely stash outstanding changes first. The script fetches GitHub main automatically and fast-forwards clean local `main` when it is behind. Local-only commits still need to be pushed/reviewed/merged separately. Do not include unrelated edits just to satisfy this preflight.

## Automatic source recovery

Every invocation, including `-CheckOnly`, first refreshes Git's cached file status
and fetches `refs/heads/main` from the configured LifeGather origin. This downloads
Git source changes, not Docker layers. Only a clean `main` proven to be behind can
advance, using `git merge --ff-only origin/main` after that fetch (the fast-forward
equivalent of a pull, without a second implicit fetch). It creates no merge commit.

After an update, the publisher reloads its updated script once and reads the new
version/revision before tests or image builds. It preserves the original options.
A second main advance stops with instructions to retry instead of looping.

Dirty/staged/untracked files, index errors, local-only or diverged main commits,
an unexpected origin, or a failed fetch stop before verification/build. Nothing is
stashed, discarded, reset, rebased, or pushed. Feature and detached checkouts keep
their chosen commit for ordinary builds or immutable-tag publication; `-PublishLatest`
requires `main` and never switches branches automatically. Git uses its existing
transport/credentials; the script does not silently install missing tools.

## Feature-completion policy

The user's 2026-10-18 standing instruction in `AGENTS.md` is: after a scoped feature
passes its required checks, commit, push, open a PR, merge the tested head, delete
the merged feature branch, then build/smoke-test clean GitHub-matching `main` and
publish its commit tag plus `ghcr.io/bgoldbeck/life-gather:latest`. This sequence is
authorized without repeated confirmation for each feature. Preserve branch checks,
owner isolation, size reporting, and the script's release guards. The current
script builds without an interactive prompt; `-Publish` explicitly enables upload.
Hosted GitHub Actions stays disabled; publication does not redeploy TrueNAS.

## Commands

On Windows, double-click **`scripts/Publish-Container.cmd`** to build, verify and
publish the commit tag plus `latest`. The window closes automatically on success;
on failure it stays open until you press a key so you can read the error.
An existing caller terminal stays open and receives the original exit code.
This launcher passes `-Publish
-PublishLatest`; it does not ask again before building/uploading. Run the PowerShell
script without `-Publish` for a local build only. No extra `-Verbose` flag is needed: named timestamped stages, commands,
elapsed times, plain Docker build progress and health checks are shown by default.
Registry tokens and stdin are never printed. Failed stages stop the release and
leave an error explaining what failed; publication never restarts your running app.

The final `Result:` states whether checks passed, an
image was built locally, publication succeeded, or the release failed. `Cleanup`
only names a housekeeping stage. A dirty checkout prints uncommitted paths and
reports `FAILED` before any build/upload. Commit or deliberately stash those edits;
the script will never do that for you or discard them automatically.

Publishing preflight checks the active GitHub account's actual OAuth scope header
before running the tests or build. A token missing `write:packages` stops immediately
with this recovery command:

```powershell
gh auth refresh --hostname github.com --scopes write:packages
```

Complete GitHub's browser authorization, then rerun. If `gh` is not on PATH, the
publisher also supports the cached CLI under `%TEMP%/lifegather-github-cli/bin/gh.exe`.
Scopes must be confirmed; a fine-grained token with no compatible scope header is
not sufficient for this GHCR publisher. A classic PAT with `write:packages` is an
alternative. The selected account must also have write access to the existing GHCR
package, which is separate from repository access. The script uses the actual
authenticated username for Docker sign-in and rechecks identity/scope before upload;
it never changes package permissions or prints the registry token. See
[GitHub's container authentication documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

To let the publisher start the sign-in or missing-scope flow when needed, opt in:

```powershell
.\scripts\Publish-Container.ps1 -Publish -PublishLatest -RepairAuthentication
```

You still approve GitHub access in the browser. Without this option, missing
authentication/scopes produce repair instructions before expensive checks. Existing
valid authentication is reused; no automatic package permissions, visibility or
token rotation is performed. A denied/failed repair stops the release.

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

## Bandwidth and explicit publishing

The script reads locally available image sizes without pulling. It runs backend/frontend checks and validates both Compose configurations. Dependency setup (`uv sync`/`npm ci`) may download missing packages, so choose a suitable time even for check-only runs.

There are no build/upload confirmation prompts: starting the script authorizes a
local build, and `-Publish` authorizes uploading after verification. The `.cmd`
launcher passes `-Publish -PublishLatest`. Docker may download missing base layers.
The script reports existing local sizes before building and the new image size
before uploading. Choose when to start it according to your available bandwidth.

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
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tests\Release-Source.Tests.ps1
```

The scripts are covered by mocked release/refusal/authentication cases and real
temporary Git repositories, including fast-forward content, one-time script reload,
staging preservation, feature/detached branches and divergence. Both Windows
PowerShell 5.1 and PowerShell 7 are exercised. These tests do not build/publish an
image, change real credentials or contact GitHub; source-only release-tool changes
are excluded by `.dockerignore` and do not require a runtime image rebuild.

Historical image measurement: a real local build, isolated container smoke test,
and public GHCR publication passed on 2026-10-17 from main revision `c5d4a73c944843b34cbeb355e84a5aaf0e1b09e4`.
For that release, `latest` and the commit tag resolved to manifest
`sha256:46d97058daf97bb83b7298e52d6c90357cde06f97be23837fd5d700b330310d5`;
anonymous registry access and the revision label were verified afterward.

That release has 71,719,325 bytes of compressed runtime layers (about 71.7 MB), approximately 306 MB on disk. Compared with the prior published image, two new layers totaled 25,233,301 bytes (about 25.2 MB), plus small configuration/manifest/provenance metadata. These are measurements of this release, not a promise for later updates. The first upload attempt stopped before transfer because Windows PowerShell stripped quotes from a Docker-context template; the JSON context lookup now avoids that issue.

Publication does not update an already running container. Pull and recreate/redeploy explicitly. Locally source-built images may lack revision/version labels; the published release carries its Git revision label. Real Google/SMTP/model interactions are not part of the isolated container smoke test.
