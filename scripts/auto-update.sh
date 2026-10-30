#!/usr/bin/env bash
# Pull-only TrueNAS SCALE cron job: when ghcr.io/bgoldbeck/life-gather:latest
# differs from the image the running app uses, redeploy the app from it and
# wait for it to report healthy. It builds and pushes nothing; images are still
# published by Publish-Container.ps1 or auto-publish.sh. Quiet when nothing
# changed, so cron sends no mail. Setup: docs/TRUENAS.md#automatic-updates.
#
# Needs only bash, flock, Docker, midclt and (for the health check) curl, all
# shipped with TrueNAS 24.10 and later. Run as root: Docker needs it.
#
# Settings (environment variables, all optional):
#   LIFEGATHER_TRUENAS_APP  TrueNAS app name to update (lifegather)
#   LIFEGATHER_HEALTH_URL   URL to poll after redeploying, e.g.
#                           http://127.0.0.1:8787/health/ready
#   LIFEGATHER_LOCK_FILE    lock that stops overlapping runs
#                           (/tmp/lifegather-auto-update.lock)

main() {
    set -Eeuo pipefail

    local app=${LIFEGATHER_TRUENAS_APP:-lifegather}
    local image=ghcr.io/bgoldbeck/life-gather:latest

    # A slow pull or redeploy may outlast the cron interval; the next run exits.
    exec 9>"${LIFEGATHER_LOCK_FILE:-/tmp/lifegather-auto-update.lock}"
    flock --nonblock 9 || return 0

    command -v midclt >/dev/null 2>&1 || fail 'midclt not found; this only works on TrueNAS SCALE.'

    # TrueNAS names each app's Compose project ix-<app>.
    local container
    container=$(docker ps --quiet \
        --filter "label=com.docker.compose.project=ix-$app" \
        --filter label=com.docker.compose.service=backend | head -n 1)
    # A stopped app stays stopped: starting it is the owner's decision.
    [[ -n $container ]] || return 0

    local configured
    configured=$(docker inspect --format '{{.Config.Image}}' "$container")
    # A digest or commit tag is a deliberate pin; never replace it with latest.
    [[ $configured == "$image" ]] ||
        fail "App '$app' uses $configured, not $image; change its image to the latest tag to enable updates."

    docker pull --quiet "$image" >/dev/null || fail "Could not pull $image."
    local running pulled
    running=$(docker inspect --format '{{.Image}}' "$container")
    pulled=$(docker image inspect --format '{{.Id}}' "$image")
    [[ $running == "$pulled" ]] && return 0

    log "Updating app '$app' from $running to $pulled."
    # The app's Compose file uses pull_policy: always, so a redeploy recreates
    # it from the image just pulled. Volumes and datasets are untouched.
    midclt call -j app.redeploy "$app" >/dev/null || fail "Redeploying app '$app' failed."

    local url=${LIFEGATHER_HEALTH_URL:-}
    [[ -n $url ]] || { log 'Redeployed; LIFEGATHER_HEALTH_URL is not set, so health was not checked.'; return 0; }
    command -v curl >/dev/null 2>&1 || { log 'Redeployed; curl not found, so health was not checked.'; return 0; }
    for _ in $(seq 90); do
        if curl --fail --silent --max-time 3 --output /dev/null "$url"; then
            log "Redeployed app is healthy at $url."
            return 0
        fi
        sleep 2
    done
    fail "Redeployed app did not become healthy at $url."
}

log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
# Failures go to stderr, which the TrueNAS cron job turns into an alert mail.
fail() { log "ERROR: $*" >&2; exit 1; }

main "$@"
exit
