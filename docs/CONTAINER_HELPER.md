# Windows container helper

Double-click **scripts\Container-Helper.cmd**, or **scripts\Publish-Container.cmd**
without arguments. The numbered terminal menu stays open after success or failure.
It uses Windows PowerShell 5.1; no GUI framework or PowerShell upgrade is required.

1. Check the status table. Open **Setup** to install Git, Docker Desktop, or
   GitHub CLI individually through Windows App Installer (`winget`). Each installer
   shows its own download/progress output. Without winget, the helper prints the
   official download page. Installations occur only when selected.
2. Start Docker Desktop from Setup, finish any WSL/virtualization setup, and
   refresh status. Windows may request elevation or a reboot; the helper does not
   change Windows features or restart the computer. Use Linux containers.
3. Choose **Verify only**, **Build locally**, or **Build & publish latest**.
   Verification and local builds need Git and Docker, with no GitHub sign-in.
   A private repository still needs normal Git access to fetch source.
4. Publishing also needs GitHub CLI. Use **GitHub sign-in / fix package
   permission** for browser authorization with `write:packages`. The selected
   account must have write access to the GHCR package. Application Google/OAuth
   client credentials are unrelated and are not needed to build or publish.

The publisher still refuses dirty source, fast-forwards only clean main, preserves
feature/detached builds, requires current GitHub main for latest, and stops on
failed tests. Source push/merge and running-app deployment remain separate actions.
The existing **Publish-And-Start.cmd** retains its explicit preview-start behavior.

## Fewer host dependencies

Python, uv, Node and npm run inside Docker. The release controller reuses the
existing four-shard Linux/PostgreSQL test runner, plus strict Ruff/format/mypy
checks from `backend/`. A separate Node image runs frontend tests, lint, types,
format checks and a production build from `frontend/`. Checks execute even when
Docker reuses cached images. Verification images are local only; they are not
included in the runtime image or uploaded to GHCR. Build contexts use allowlists.

The controller mounts the checkout read-only, an ignored report folder writable,
and the **local Docker engine socket**. Socket access allows it to create and
remove disposable test resources; run it only from trusted LifeGather source.
Remote Docker engines are unsupported because source/report bind mounts must
refer to the local filesystem. On Windows use Docker Desktop with Linux containers.
First runs download images and locked dependencies; subsequent runs reuse layers.
Reports and shard logs are under `test-results/release-<run-id>/`.

## Avoid rebuilding an existing publication

Publishing compares the full Git commit with the immutable `sha-<full-commit>`
tag's Linux/amd64 revision and application-version labels in GHCR. An application
version number alone never decides whether to skip a build.

- If the commit tag exists and latest has the same manifest digest, skip tests,
  build and upload and report **ALREADY PUBLISHED**. Existing-publication checks
  trust the previously published image; they do not rerun its tests.
- If the verified commit image exists but latest is missing/different, recheck
  main, local source and account, then copy its manifest to latest. Verify the
  resulting digest; no image build, pull or layer upload is required.
- If the commit tag is absent (registry HTTP 404), run all checks, build and
  isolated container smoke tests, then upload. Verify remote labels and digests.
- Authentication/network/server errors and invalid commit metadata stop the
  release. They never count as an existing publication or a missing image.
- **Force rebuild & publish latest** requires typing `REBUILD` in the menu. This
  rebuilds the same revision, reruns checks and replaces its registry tags, useful
  when deliberately rerunning a release. Docker can still reuse build cache;
  force rebuild bypasses the publication skip, not Docker's layer cache.

Direct scripted use remains available:

```powershell
.\scripts\Container-Helper.ps1 -StatusOnly
.\scripts\Publish-Container.ps1 -CheckOnly
.\scripts\Publish-Container.ps1                  # verify, build, smoke; no upload
.\scripts\Publish-Container.ps1 -Publish -PublishLatest -RepairAuthentication
.\scripts\Publish-Container.ps1 -Publish -PublishLatest -ForceRebuild
```

The `.cmd` publisher forwards explicitly supplied arguments to the PowerShell
publisher; without arguments it opens the menu. Image-size output describes local
engine size, not compressed network transfer. Only missing layers are uploaded.
Publication never redeploys your running app.
