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

GitHub Actions is disabled by maintainer choice; pushes and pull requests do not publish images automatically. Maintainers run checks locally and ask for approval before rebuilding or uploading an image, reporting its size. Approved local releases publish `latest` and a `sha-<full-commit-sha>` tag. Publishing a newer image does not automatically restart an installed TrueNAS app: use its image update/pull controls, or pull and recreate the Compose service. To have the NAS do all of this by itself, see [Automatic rebuilds](#automatic-rebuilds).

```sh
docker compose -f deploy/compose.image.yaml pull
docker compose -f deploy/compose.image.yaml up -d --wait
```

For a repeatable deployment or rollback, pin the image by its published digest (`ghcr.io/bgoldbeck/life-gather@sha256:...`) or select a previously published commit tag. Keep the same persistent storage mounts. Do not remove the data or database volumes when updating. Migrations run automatically on startup; an image rollback across a migration needs the database backup taken before the update.

Public images contain application code and bundled assets, not users' `/data` volumes, local `.env` files or provider credentials.

## Automatic rebuilds

`scripts/auto-publish.sh` is the unattended Linux counterpart of
`Publish-And-Start`, meant for a TrueNAS SCALE cron job. Each run fetches
GitHub `main`. When it holds a commit that has not been published yet, the
script:

1. fast-forwards the NAS's clean clone to it;
2. runs the same checks as the [release script](LOCAL_RELEASE.md): backend tests
   against a throwaway PostgreSQL, ruff, mypy, the frontend tests, lint,
   typecheck, format and build, and both Compose files;
3. builds the `linux/amd64` image and smoke-tests it in an isolated container;
4. pushes `ghcr.io/bgoldbeck/life-gather:sha-<commit>`, then `latest` if GitHub
   `main` has not moved meanwhile;
5. optionally redeploys the TrueNAS app and waits for it to report healthy.

Otherwise it exits without output. Any failed step stops the run: nothing is
pushed and the app is not touched. The failing commit is remembered, so later
runs stay quiet until `main` gets a new commit (or you rerun with `--force`).
A lock file makes an overlapping run exit at once, so a slow build is never
started twice. A full run takes roughly 20 to 30 minutes, most of it the
backend tests, and keeps a few CPU cores busy.

### Why containers

TrueNAS SCALE is an appliance: its base OS is read-only and package
installation is disabled, so uv, Python 3.13 and Node.js cannot be installed on
it. The script therefore needs only what TrueNAS 24.10 and later already ship:
bash, `flock` and Docker. Each check runs in a throwaway container (Python with
the Dockerfile's uv release, `node:24-bookworm-slim`, `pgvector/pgvector:pg17`)
on a copy of the source, so nothing is installed on the NAS and the clone stays
clean. Downloaded packages are cached in the Docker volumes
`lifegather-autobuild-uv` and `lifegather-autobuild-npm`. Git is used if the
NAS has it, otherwise the `alpine/git` image runs it.

### Setup

Run these in **System → Shell** as root (`sudo -i`). The examples use a pool
named `tank`; use your own.

1. In **Datasets**, create a dataset for the build, for example
   `tank/lifegather-build`. Its files are the clone, the log and the registry
   login, not your records.
2. Clone the repository into it:

   ```sh
   git clone https://github.com/bgoldbeck/life-gather.git /mnt/tank/lifegather-build/source
   ```

   Without git on the NAS:
   `docker run --rm -v /mnt/tank/lifegather-build:/w -w /w alpine/git clone https://github.com/bgoldbeck/life-gather.git source`.
   Leave the clone on `main` and never edit files in it: a dirty or diverged
   clone stops every run.
3. Create a GitHub personal access token (classic) with only the
   `write:packages` scope (**GitHub → Settings → Developer settings → Personal
   access tokens → Tokens (classic)**). Store the GHCR login in the script's own
   folder, not in root's Docker configuration:

   ```sh
   cfg=/mnt/tank/lifegather-build/lifegather-autobuild/docker-config
   mkdir -p "$cfg" && chmod 700 "$cfg"
   read -rs GHCR_TOKEN   # paste the token, then press Enter
   printf '%s' "$GHCR_TOKEN" | docker --config "$cfg" login ghcr.io --username bgoldbeck --password-stdin
   unset GHCR_TOKEN
   ```

   Docker keeps the token, base64-encoded, in `$cfg/config.json`. Anyone with
   root on the NAS can read it; revoke it on GitHub if the NAS is compromised.
4. Run it once by hand and watch the log:

   ```sh
   bash /mnt/tank/lifegather-build/source/scripts/auto-publish.sh --force
   tail -f /mnt/tank/lifegather-build/lifegather-autobuild/auto-publish.log
   ```

5. Add the cron job in **System → Advanced Settings → Cron Jobs → Add**:

   | Field | Value |
   | --- | --- |
   | Description | LifeGather auto-publish |
   | Command | `LIFEGATHER_TRUENAS_APP=lifegather LIFEGATHER_HEALTH_URL=http://127.0.0.1:8787/health/ready bash /mnt/tank/lifegather-build/source/scripts/auto-publish.sh` |
   | Run As User | `root` (Docker needs it) |
   | Schedule | Custom, `*/15 * * * *` (every 15 minutes) |
   | Hide Standard Output | checked |
   | Hide Standard Error | unchecked, so a failure sends a TrueNAS alert mail |
   | Enabled | checked |

   Use the app's name exactly as **Apps → Installed** shows it. Leave out
   `LIFEGATHER_TRUENAS_APP` to publish without restarting the app (another
   machine, or you redeploy by hand). The health URL is optional; use the host
   port you chose.

### Settings and files

| Setting | Meaning |
| --- | --- |
| `LIFEGATHER_TRUENAS_APP` | App to redeploy (`midclt call -j app.redeploy <name>`, the same job as the app's **Redeploy** button). The build already tagged the new image `latest` on the NAS, and the image-only Compose file also uses `pull_policy: always`, so the app is recreated from the new `latest`. The app must use the `latest` tag, not a pinned digest. Volumes and datasets are kept. |
| `LIFEGATHER_HEALTH_URL` | Polled for three minutes after the redeploy; the run fails if it never answers. |
| `LIFEGATHER_AUTOBUILD_DIR` | State folder. Default: `lifegather-autobuild` next to the clone. |

The state folder holds `auto-publish.log` (rotated at 20 MB),
`last-published-revision`, `last-failed-revision`, `last-check` (time of the
last run, quiet or not), the lock file and `docker-config`.

### Before turning on redeploys

Migrations run automatically when the new image starts, and an image rollback
across a migration needs the database backup taken before it. Give the
database and `/data` datasets a periodic snapshot task (**Data Protection →
Periodic Snapshot Tasks**), for example hourly, before enabling
`LIFEGATHER_TRUENAS_APP`.

Each published build untags the previous one. Docker's build cache still grows
over time; reclaim it occasionally with `docker builder prune`. To stop
automatic publishing, disable the cron job. The offline test for the script is
`bash scripts/tests/auto-publish.test.sh`.

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
