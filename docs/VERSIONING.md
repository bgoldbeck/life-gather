# Application versions

LifeGather uses three numbers: `major.minor.patch`, displayed as `v0.3.0`.

| Change | Example |
| --- | --- |
| New user-facing feature or feature release | `0.3.0` → `0.4.0` |
| Bug fix to that release | `0.4.0` → `0.4.1` |
| Further bug fix | `0.4.1` → `0.4.2` |
| Breaking change after a stable release | `1.2.3` → `2.0.0` |

Before 1.0, minor releases can change interfaces; document migration consequences.
Do not switch to 1.0 or make a breaking major release without an explicit decision.
Documentation-only changes do not bump the version. Several features deliberately
released together can share one minor bump. This begins the visible versioning
baseline at `0.3.0`; it does not retroactively relabel earlier images.

The single source is `backend/src/lifegather/version.py`. Python package metadata,
FastAPI metadata, `/api/version`, and `/auth/session` use that same value. The UI
displays the backend's version on the login screen and in the app header. A build
without an embedded Git revision explicitly says **Source build**.

For every feature/bug-fix release, update that file and `CHANGELOG.md`, then run
the relevant verification. The backend's dynamic Hatch version means there is
no second application version to edit in `pyproject.toml`. The frontend package
version is internal build-tool metadata, not the application version. CI and
Git hooks do not bump versions automatically.

The release script reads the version file, applies the OCI application version
and revision labels, and embeds the exact commit via the `APP_REVISION` Docker
build argument. Its smoke test verifies the running API reports those values.
Direct source builds show the right version but no revision unless that build
argument is supplied. `LIFEGATHER_BUILD_REVISION` is build metadata, not a secret
or a deployment setting to customize.

`latest` remains a movable image tag. The existing `sha-<full-commit>` image tag
and digest identify an exact build. A short Git revision beside the app version
distinguishes different builds of the same version. A source merge does not update
an existing container; the release still needs a new image and explicit redeploy.

Since v0.58.1, Vite reads the same backend version file when compiling the UI.
Docker passes `APP_REVISION` into both frontend and backend builds; no second
version string is maintained. The UI displays its loaded bundle's build, rather
than adopting newer server metadata while still executing old code. Session checks
on focus/every minute show an update notice when versions differ, or when both
known revisions differ (including rollback). Missing revision metadata alone is
not evidence of a new build. No automatic reload discards unsaved drafts; the
notice's Reload action uses an ordinary page reload.

Startup HTML and non-hashed static resources use `no-cache, must-revalidate`,
including conditional 304 responses and missing files. Successful hashed assets
under `/assets/` use one-year immutable caching. HTTP APIs keep `no-store`.
Pre-v0.58.1 tabs need a reload once to acquire the fix; these headers cannot update
JavaScript already executing in memory. No service worker, live-redeploy mechanism
or browser-storage clearing is introduced.

The v0.58.1 verification passed 644 backend tests, strict mypy/Ruff/format and
package builds; 307 frontend tests, lint/types/format and production build.
Synthetic browser deployment testing verified the minute-based notice, pinned
loaded version, retained unsent draft and explicit ordinary reload. Local HTTP
checks verified revalidation and immutable asset headers. Source graph/HTML were
refreshed (3,623 nodes / 14,856 edges; two files have partial/no symbol extraction).

The README source-version badge links to the changelog. Update its value with the single version source during releases; the backend version test checks synchronization. It describes source, not Docker deployment.
