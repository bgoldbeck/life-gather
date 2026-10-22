#!/usr/bin/env bash
# Unattended Linux counterpart of Publish-And-Start: meant for a TrueNAS SCALE
# cron job. Each run fetches GitHub main; when it has a commit that has not been
# published yet, it fast-forwards the clean checkout, runs the same checks as
# Publish-Container.ps1 inside throwaway containers, builds and smoke-tests the
# image, pushes the commit tag plus latest to GHCR, and optionally redeploys
# the TrueNAS app. A failed run never pushes or redeploys anything.
#
# Needs only bash, flock and Docker on the host (git is used if installed,
# otherwise it runs in a container). Setup: docs/TRUENAS.md#automatic-rebuilds.
#
# Options: --force  rebuild even if main is already published or just failed.
#
# Settings (environment variables, all optional):
#   LIFEGATHER_AUTOBUILD_DIR  state, log and registry login (default: a
#                             lifegather-autobuild folder next to the clone)
#   LIFEGATHER_TRUENAS_APP    TrueNAS app name to redeploy after publishing
#   LIFEGATHER_HEALTH_URL     URL to poll after redeploying, e.g.
#                             http://127.0.0.1:8787/health/ready
#   LIFEGATHER_RETRY_HOURS    hours before a failed commit is tried again (6)

# Everything lives in main(): bash reads scripts lazily, and the fast-forward
# below can replace this file while it runs. Changes apply from the next run.
main() {
    set -Eeuo pipefail
    umask 077

    local force=false
    case "${1:-}" in
        '') ;;
        --force) force=true ;;
        *) echo "Usage: $0 [--force]" >&2; return 2 ;;
    esac

    local script_dir repo_root
    script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
    repo_root=$(dirname -- "$script_dir")
    STATE_DIR=${LIFEGATHER_AUTOBUILD_DIR:-$(dirname -- "$repo_root")/lifegather-autobuild}
    mkdir -p -- "$STATE_DIR"
    LOG_FILE=$STATE_DIR/auto-publish.log
    REPO=$repo_root
    RUN_ID=lifegather-autobuild-$$-$RANDOM
    CLEANUP_CONTAINERS=()
    CLEANUP_NETWORKS=()

    # Overlapping cron runs exit at once while an earlier run still holds this.
    exec 9>"$STATE_DIR/auto-publish.lock"
    if ! flock --nonblock 9; then
        return 0
    fi
    date -u '+%Y-%m-%dT%H:%M:%SZ' >"$STATE_DIR/last-check"

    git_cmd fetch --quiet origin refs/heads/main:refs/remotes/origin/main
    local target published failed
    target=$(git_cmd rev-parse --verify 'refs/remotes/origin/main^{commit}')
    published=$(read_state last-published-revision)
    failed=$(read_state last-failed-revision)
    # Nothing new: stay quiet so cron sends no mail. A failed commit is retried
    # every few hours in case the failure was a download or network problem.
    if [[ $force == false ]]; then
        [[ $target == "$published" ]] && return 0
        if [[ $target == "$failed" ]] && [[ -n $(find "$STATE_DIR/last-failed-revision" \
            -mmin "-$((${LIFEGATHER_RETRY_HOURS:-6} * 60))") ]]; then
            return 0
        fi
    fi

    rotate_log
    exec 4>&2 >>"$LOG_FILE" 2>&1
    trap 'on_exit $?' EXIT
    STAGE=Preflight
    log "Run started for origin/main $target (last published: ${published:-none})."
    preflight "$target"

    # From here on a failure belongs to this commit: remember it so cron does
    # not rebuild the same broken revision every few minutes.
    FAILED_REVISION=$target
    local version
    version=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p' backend/src/lifegather/version.py)
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail 'Expected a valid application version.'
    log "Release revision: $target (version $version)."

    backend_checks
    frontend_checks
    compose_checks
    build_image "$target" "$version"
    smoke_test "$target" "$version"
    publish_image "$target"
    write_state last-published-revision "$target"
    rm -f -- "$STATE_DIR/last-failed-revision"
    FAILED_REVISION=
    remove_previous_tag "$published" "$target"
    redeploy
    STAGE=Done
    log "Published $IMAGE:sha-$target and $IMAGE:latest."
}

IMAGE=ghcr.io/bgoldbeck/life-gather
POSTGRES_IMAGE=pgvector/pgvector:pg17
NODE_IMAGE=node:24-bookworm-slim
GIT_IMAGE=alpine/git:latest
FAILED_REVISION=
STAGE=Preflight

log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
fail() { log "ERROR: $*"; exit 1; }
stage() { STAGE=$1; log "Stage: $1"; }
read_state() { [[ -f $STATE_DIR/$1 ]] && cat -- "$STATE_DIR/$1" || true; }
write_state() { printf '%s\n' "$2" >"$STATE_DIR/$1.tmp" && mv -f -- "$STATE_DIR/$1.tmp" "$STATE_DIR/$1"; }

# Run a command, logging it; any failure stops the run before publishing.
run() {
    log "> $*"
    "$@" || fail "$1 failed (exit $?) during stage '$STAGE'. Nothing was published."
}

# Prefer the host's git; TrueNAS keeps its base OS read-only, so fall back to a
# container that sees the clone at the same path.
git_cmd() {
    if command -v git >/dev/null 2>&1; then
        git -c "safe.directory=$REPO" -C "$REPO" "$@"
    else
        docker run --rm --volume "$REPO:$REPO" --workdir "$REPO" "$GIT_IMAGE" \
            -c "safe.directory=$REPO" "$@"
    fi
}

rotate_log() {
    if [[ -f $LOG_FILE ]] && (($(stat -c %s -- "$LOG_FILE") > 20 * 1024 * 1024)); then
        mv -f -- "$LOG_FILE" "$LOG_FILE.1"
    fi
}

# shellcheck disable=SC2329 # Called from the EXIT trap.
on_exit() {
    local status=$1
    trap - EXIT
    set +e
    for name in "${CLEANUP_CONTAINERS[@]}"; do
        docker rm --force --volumes "$name" >/dev/null 2>&1 || log "Remove leftover container $name manually."
    done
    for name in "${CLEANUP_NETWORKS[@]}"; do
        docker network rm "$name" >/dev/null 2>&1 || log "Remove leftover network $name manually."
    done
    if ((status != 0)); then
        [[ -n $FAILED_REVISION ]] && write_state last-failed-revision "$FAILED_REVISION"
        log "Result: FAILED during stage '$STAGE'."
        # stderr reaches cron's mail; the details stay in the log.
        echo "LifeGather auto-publish failed during '$STAGE'. See $LOG_FILE" >&4
    else
        log 'Result: OK.'
    fi
    exit "$status"
}

preflight() {
    local target=$1
    for command in docker flock; do
        command -v "$command" >/dev/null 2>&1 || fail "$command is not installed."
    done
    [[ $(docker info --format '{{.OSType}}') == linux ]] || fail 'Docker is not running a Linux engine.'
    docker compose version >/dev/null 2>&1 || fail 'docker compose is unavailable.'
    # Check the registry login now rather than after a long build.
    grep -q '"ghcr.io"' "$STATE_DIR/docker-config/config.json" 2>/dev/null \
        || fail "No GHCR login in $STATE_DIR/docker-config. See docs/TRUENAS.md#automatic-rebuilds."

    [[ $(git_cmd branch --show-current) == main ]] || fail 'The clone must have main checked out.'
    local dirty
    dirty=$(git_cmd status --porcelain)
    [[ -z $dirty ]] || fail "The clone has local changes; nothing was built:"$'\n'"$dirty"
    git_cmd merge-base --is-ancestor HEAD "$target" || fail 'Local main has commits GitHub main lacks; nothing was built.'
    if [[ $(git_cmd rev-parse HEAD) != "$target" ]]; then
        run git_cmd merge --ff-only --quiet "$target"
    fi
    cd -- "$REPO"
    [[ $(git_cmd rev-parse HEAD) == "$target" ]] || fail 'Checkout does not match GitHub main.'
}

# Throwaway pgvector database on a private network, as Publish-Container does.
start_database() {
    local name=$1 network=$2 password=$3
    CLEANUP_CONTAINERS+=("$name")
    run docker run --detach --quiet --name "$name" --network "$network" --network-alias db \
        --env "POSTGRES_PASSWORD=$password" --env 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C' \
        "$POSTGRES_IMAGE"
    for _ in $(seq 60); do
        docker exec "$name" pg_isready --host 127.0.0.1 --username postgres >/dev/null 2>&1 && return 0
        sleep 1
    done
    fail 'The temporary PostgreSQL database did not become ready.'
}

create_network() {
    CLEANUP_NETWORKS+=("$1")
    run docker network create "${@:2}" "$1"
}

# Checks run on a read-only view of the clone, copied inside the container, so
# no root-owned dependency folders are left behind in the checkout.
COPY_SOURCE='mkdir -p /work && tar -C /src --exclude=./.git --exclude=./frontend/node_modules --exclude=./backend/.venv -cf - . | tar -C /work -xf -'

backend_checks() {
    stage 'Backend verification'
    # The same uv release the Dockerfile copies into the image.
    local uv_image
    uv_image=$(sed -n 's/^COPY --from=\(ghcr\.io\/astral-sh\/uv:[^ ]*\) .*/\1/p' Dockerfile | head -n 1)
    [[ -n $uv_image ]] || fail 'Could not find the uv image in the Dockerfile.'
    printf 'FROM python:3.13-slim-bookworm\nCOPY --from=%s /uv /uvx /bin/\n' "$uv_image" \
        | run docker build --quiet --tag lifegather-autobuild-python -

    local network=$RUN_ID-tests password
    password=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
    # Not --internal: uv downloads missing dependencies before the tests.
    create_network "$network"
    start_database "$RUN_ID-test-db" "$network" "$password"
    run docker run --rm --network "$network" --volume "$REPO:/src:ro" \
        --volume lifegather-autobuild-uv:/root/.cache/uv \
        --env "LIFEGATHER_TEST_DATABASE_URL=postgresql://postgres:$password@db:5432/postgres" \
        lifegather-autobuild-python bash -c "$COPY_SOURCE && cd /work/backend && uv sync --locked && \
uv run --locked pytest && uv run --locked ruff check . && uv run --locked ruff format --check . && uv run --locked mypy"
}

frontend_checks() {
    stage 'Frontend verification'
    run docker run --rm --volume "$REPO:/src:ro" --volume lifegather-autobuild-npm:/root/.npm "$NODE_IMAGE" \
        bash -c "$COPY_SOURCE && cd /work/frontend && npm ci --no-audit --no-fund && npm test && \
npm run lint && npm run typecheck && npm run format:check && npm run build"
}

compose_checks() {
    stage 'Compose validation'
    run env LIFEGATHER_DB_PASSWORD="${LIFEGATHER_DB_PASSWORD:-composevalidation}" docker compose config --quiet
    run env LIFEGATHER_DB_PASSWORD="${LIFEGATHER_DB_PASSWORD:-composevalidation}" \
        docker compose -f deploy/compose.image.yaml config --quiet
}

build_image() {
    local revision=$1 version=$2
    stage 'Build'
    run docker build --platform linux/amd64 \
        --label org.opencontainers.image.source=https://github.com/bgoldbeck/life-gather \
        --label "org.opencontainers.image.revision=$revision" \
        --label "org.opencontainers.image.version=$version" \
        --build-arg "APP_REVISION=$revision" --tag "$IMAGE:sha-$revision" .
    log "Built $IMAGE:sha-$revision ($(docker image inspect --format '{{.Size}}' "$IMAGE:sha-$revision") bytes unpacked)."
}

smoke_test() {
    local revision=$1 version=$2
    stage 'Isolated container smoke verification'
    local network=$RUN_ID-smoke probe=$RUN_ID-app password
    password=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
    create_network "$network" --internal
    start_database "$RUN_ID-smoke-db" "$network" "$password"
    CLEANUP_CONTAINERS+=("$probe")
    run docker run --detach --quiet --pull=never --name "$probe" --network "$network" \
        --env "LIFEGATHER_DATABASE_URL=postgresql://postgres:$password@db:5432/postgres" \
        --read-only --tmpfs /tmp:size=64m,mode=1777 --tmpfs /data:size=64m,uid=10001,gid=10001,mode=0700 \
        --cap-drop ALL --security-opt no-new-privileges:true "$IMAGE:sha-$revision"
    local status=
    for attempt in $(seq 45); do
        status=$(docker inspect --format '{{.State.Health.Status}}' "$probe")
        log "Health check $attempt/45: $status"
        [[ $status == healthy || $status == unhealthy ]] && break
        sleep 2
    done
    [[ $status == healthy ]] || fail 'The isolated test container did not become healthy.'
    log 'Running smoke checks inside the container.'
    sed -e "s/__RELEASE_VERSION__/$version/" -e "s/__RELEASE_REVISION__/$revision/" <<'PY' \
        | docker exec --interactive "$probe" python - || fail 'Container smoke test failed.'
import json, os, shutil, urllib.request
from pathlib import Path
assert os.getuid() == 10001
assert shutil.which('node') is None
base = 'http://127.0.0.1:8787'
with urllib.request.urlopen(base + '/health') as r:
    assert json.load(r) == {'status': 'ok'}
with urllib.request.urlopen(base + '/') as r:
    assert b'<title>LifeGather</title>' in r.read()
with urllib.request.urlopen(base + '/brand/lifegather-icon.png') as r:
    assert r.read(8) == b'\x89PNG\r\n\x1a\n'
with urllib.request.urlopen(base + '/auth/session') as r:
    status = json.load(r)
    build = status.pop('build')
    assert status == {
        'configured': False,
        'test_login_enabled': False,
        'email_password_enabled': False,
        'email_delivery_enabled': False,
        'user': None,
        'csrf_token': None,
    }
with urllib.request.urlopen(base + '/api/version') as r:
    assert json.load(r) == build
assert build['version'] == '__RELEASE_VERSION__'
assert build['revision'] == '__RELEASE_REVISION__'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['LIFEGATHER_DATABASE_URL'].replace('postgresql://', 'postgresql+psycopg://', 1))
with engine.connect() as connection:
    assert connection.scalar(text('SELECT count(*) FROM alembic_version')) == 1
    assert connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")) == 1
    assert connection.scalar(text('SELECT count(*) FROM users')) == 0
engine.dispose()
probe = Path('/data/.release-probe')
probe.write_text('synthetic check')
probe.unlink()
print('Container health, UI, PostgreSQL migration, user, and private storage verified.')
PY
}

publish_image() {
    local revision=$1
    stage 'Registry upload'
    [[ -z $(git_cmd status --porcelain) && $(git_cmd rev-parse HEAD) == "$revision" ]] \
        || fail 'Source changed during the run. Nothing uploaded.'
    # The login lives only in this folder, never in the host's Docker config.
    local auth=(--config "$STATE_DIR/docker-config")
    run docker "${auth[@]}" push --quiet "$IMAGE:sha-$revision"
    # Recheck GitHub main before moving the shared latest tag.
    local remote_main
    remote_main=$(git_cmd ls-remote origin refs/heads/main | cut -f1)
    [[ $remote_main == "$revision" ]] || fail 'GitHub main moved; the commit tag was uploaded but latest was not changed.'
    run docker tag "$IMAGE:sha-$revision" "$IMAGE:latest"
    run docker "${auth[@]}" push --quiet "$IMAGE:latest"
}

# Keep NAS disk use flat: untag the previous build (layers shared with the new
# image stay). Docker's build cache is left alone.
remove_previous_tag() {
    local previous=$1 current=$2
    [[ -n $previous && $previous != "$current" ]] || return 0
    docker image rm "$IMAGE:sha-$previous" >/dev/null 2>&1 || true
}

redeploy() {
    local app=${LIFEGATHER_TRUENAS_APP:-}
    if [[ -z $app ]]; then
        log 'LIFEGATHER_TRUENAS_APP is not set; the running app was not changed.'
        return 0
    fi
    stage 'Redeploy'
    command -v midclt >/dev/null 2>&1 || fail 'midclt not found; redeploy only works on TrueNAS SCALE.'
    # The app's Compose file uses pull_policy: always, so a redeploy recreates
    # it from the latest image. Volumes and datasets are untouched.
    run midclt call -j app.redeploy "$app"
    local url=${LIFEGATHER_HEALTH_URL:-}
    [[ -n $url ]] || return 0
    command -v curl >/dev/null 2>&1 || { log 'curl not found; health was not checked.'; return 0; }
    for _ in $(seq 90); do
        if curl --fail --silent --max-time 3 --output /dev/null "$url"; then
            log "Redeployed app is healthy at $url."
            return 0
        fi
        sleep 2
    done
    fail "Redeployed app did not become healthy at $url."
}

main "$@"
exit
