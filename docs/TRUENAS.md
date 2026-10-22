# Install the ready-built image on TrueNAS

TrueNAS Docker-based Apps can install a container image directly. A GitHub source URL is not the container image reference.

| Setting | Value |
| --- | --- |
| Image repository | `ghcr.io/bgoldbeck/life-gather` |
| Tag | `latest` |
| Architecture | `linux/amd64` (x86-64) |
| Container port | `8787/TCP` |
| Suggested host port | `8787/TCP` |
| Run-as UID/GID | `10001:10001` |
| Persistent mount | `/data` |
| Database | PostgreSQL with pgvector (`pgvector/pgvector:pg17`), see [PostgreSQL](POSTGRESQL.md) |

The current app is a foundation preview with no authentication or personal-memory storage. Use a private test network only. Do not expose it to the internet or enter personal records. Google sign-in and per-user data isolation are the next milestone.

The source now includes the first Google login slice, but the existing published preview has not been rebuilt for it. New image builds require the configuration described in [Google login setup](GOOGLE_LOGIN.md); do not assume pulling the old preview enables authentication. Deployment over a LAN IP needs an HTTPS public origin for Google login; remote-access setup remains deferred.

## PostgreSQL

LifeGather needs a PostgreSQL database. The YAML install below runs it as a
second container (`db`) in the same app with its own volume, reachable only by
LifeGather. Before installing, add an environment variable
`LIFEGATHER_DB_PASSWORD` with a long random value of letters and digits (for
example the output of `openssl rand -hex 24`) and keep a copy: changing it later
does not change the password of an existing database. For managed NAS storage,
bind-mount a dedicated dataset to `/var/lib/postgresql/data` in the `db` service
instead of the named `lifegather-db` volume, and include it in your snapshots and
replication. Never delete it: it holds your records.

### Upgrading an existing SQLite installation

Releases up to 0.74 kept everything in `/data/auth.sqlite3`. To move to
PostgreSQL:

1. Take and verify an encrypted backup with the old release
   ([operator recovery](OPERATOR_RECOVERY.md)), and snapshot the `/data` dataset.
2. Edit the app's YAML to the new [image-only Compose file](../deploy/compose.image.yaml),
   keeping your existing `/data` mount, port and other settings, and set
   `LIFEGATHER_DB_PASSWORD`.
3. Save and redeploy. On its first start the app copies `/data/auth.sqlite3`
   into the empty database in one transaction and logs `Imported N rows`. If the
   copy fails nothing is kept and the app stays down; the old file is untouched,
   so you can roll back by restoring the previous YAML and image tag.
4. Sign in and check items, photos and documents, then take a new backup. You can
   delete `/data/auth.sqlite3` afterwards; it is ignored once PostgreSQL has data.

## TrueNAS installation

These instructions target the Docker-based Apps system in TrueNAS 24.10 and later, not the older Kubernetes-based system or TrueNAS CORE jails.

1. Open **Apps → Discover Apps → Custom App** and configure the image above, or choose **Install via YAML** and paste [the image-only Compose file](../deploy/compose.image.yaml).
2. The Compose example publishes `0.0.0.0:8787:8787`, accepting connections on all IPv4 interfaces without entering a specific NAS IP. In the Custom App wizard, use host bind address `0.0.0.0`, host port `8787`, and container port `8787/TCP`. If host port 8787 is already occupied, choose another unused host port. Do not forward this preview's port through your internet router.
3. Keep the image's default command and health check. Do not enable privileged mode or add Linux capabilities.
4. Keep the run-as user at UID/GID `10001:10001`. If the wizard overrides it, configure its custom user accordingly.
5. Mount writable persistent storage at `/data`. The YAML example uses a named Docker volume for testing. For managed NAS storage, first create a dedicated TrueNAS dataset, grant UID/GID 10001 the required read/write/traverse access, and bind-mount that dataset to `/data`. Do not use a recursive permission reset on an existing shared dataset.
6. Set `LIFEGATHER_DB_PASSWORD` as described in [PostgreSQL](#postgresql). The Custom App wizard runs one container, so use **Install via YAML** for the bundled database, or point `LIFEGATHER_DATABASE_URL` at an existing PostgreSQL server prepared as in [PostgreSQL](POSTGRESQL.md).
7. Install, wait for healthy status, then open `http://YOUR_NAS_PRIVATE_IP:8787`. `/health` should return `{"status":"ok"}`.

No source build or registry credentials are needed once the package is public. The image serves both the web UI and backend, and does not need a separate Node.js container.

For an existing installation showing `127.0.0.1:8787`, edit its YAML port mapping to `0.0.0.0:8787:8787`, then save and redeploy. Pull the updated image as well as changing the mapping: older images listen on container port 8000. Keep the old mapping until the updated image is installed. Open the NAS's actual LAN IP in your browser, not `0.0.0.0`. Connections still require a reachable network, firewall permission, and an unused host port. To restrict access to the NAS itself, use `127.0.0.1:8787:8787` instead.

## Updates and rollback

GitHub Actions is disabled by maintainer choice; pushes and pull requests do not publish images automatically. Maintainers run checks locally and ask for approval before rebuilding or uploading an image, reporting its size. Approved local releases publish `latest` and a `sha-<full-commit-sha>` tag. Publishing a newer image does not automatically restart an installed TrueNAS app: use its image update/pull controls, or pull and recreate the Compose service.

```sh
docker compose -f deploy/compose.image.yaml pull
docker compose -f deploy/compose.image.yaml up -d --wait
```

For a repeatable deployment or rollback, pin the image by its published digest (`ghcr.io/bgoldbeck/life-gather@sha256:...`) or select a previously published commit tag. Keep the same persistent storage mounts. Do not remove the data or database volumes when updating. Migrations run automatically on startup; an image rollback across a migration needs the database backup taken before the update.

Public images contain application code and bundled assets, not users' `/data` volumes, local `.env` files or provider credentials.

## Publishing without hosted runners

For a checked, interactive release, use [the PowerShell release script](LOCAL_RELEASE.md). It asks before building and uploading, checks source and the container, and can publish both the commit tag and `latest` after the source is merged. The manual commands below are a lower-level alternative; maintainers must still obtain rebuild/upload approval.

If GitHub Actions is unavailable, a maintainer can build and publish from local Docker. This does not require a paid runner or a paid GitHub plan. GitHub currently lists public packages and Container Registry storage/bandwidth as free; review its [current billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-packages) before changing hosting arrangements.

Run the checks documented in the README first, then use a clean checkout of the revision being published. The GitHub CLI must have `write:packages` authorization. Keep tokens out of command arguments and files:

```powershell
$revision = git rev-parse HEAD
docker build --platform linux/amd64 --label org.opencontainers.image.source=https://github.com/bgoldbeck/life-gather --label "org.opencontainers.image.revision=$revision" --tag "ghcr.io/bgoldbeck/life-gather:sha-$revision" --tag ghcr.io/bgoldbeck/life-gather:latest .
gh auth token --hostname github.com | docker login ghcr.io --username bgoldbeck --password-stdin
```

Before pushing, run that image and verify `/health`, the homepage, the app icon, non-root execution, and writable private storage as documented in the Phase 0 checks. After verification:

```powershell
docker push "ghcr.io/bgoldbeck/life-gather:sha-$revision"
docker push ghcr.io/bgoldbeck/life-gather:latest
```

For the first package publication, set the package visibility to **Public** in GitHub's package settings so TrueNAS can pull it anonymously. Source repository visibility alone does not make the container package public.

References: [TrueNAS custom apps](https://apps.truenas.com/managing-apps/installing-custom-apps/), [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
