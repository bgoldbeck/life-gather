#!/usr/bin/env bash
# Offline checks for auto-update.sh: stub docker/midclt/curl commands record
# calls and answer from environment variables, so nothing is pulled or
# redeployed. Run: bash scripts/tests/auto-update.test.sh
set -euo pipefail

script=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/auto-update.sh
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
mkdir -p "$root/bin"

# Stub docker: log each call; STUB_FAIL makes a matching call fail.
cat >"$root/bin/docker" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_LOG"
[[ -n ${STUB_FAIL:-} && "$*" == *"$STUB_FAIL"* ]] && exit 1
case "$*" in
    'ps --quiet '*) if [[ -n ${STUB_CONTAINER:-} ]]; then echo "$STUB_CONTAINER"; fi ;;
    'inspect --format {{.Config.Image}} '*) echo "$STUB_CONFIGURED" ;;
    'inspect --format {{.Image}} '*) echo "$STUB_RUNNING" ;;
    'image inspect --format {{.Id}} '*) echo "$STUB_PULLED" ;;
esac
SH
cat >"$root/bin/midclt" <<'SH'
#!/usr/bin/env bash
printf 'midclt %s\n' "$*" >>"$STUB_LOG"
[[ -z ${STUB_FAIL:-} || "midclt $*" != *"$STUB_FAIL"* ]]
SH
cat >"$root/bin/curl" <<'SH'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >>"$STUB_LOG"
[[ -z ${STUB_FAIL:-} || "curl $*" != *"$STUB_FAIL"* ]]
SH
# The unhealthy case would otherwise wait three minutes.
printf '#!/usr/bin/env bash\n' >"$root/bin/sleep"
chmod +x "$root/bin/"*
export PATH=$root/bin:$PATH STUB_LOG=$root/calls LIFEGATHER_LOCK_FILE=$root/lock

latest=ghcr.io/bgoldbeck/life-gather:latest
export STUB_CONTAINER=abc123 STUB_CONFIGURED=$latest STUB_RUNNING=sha256:old STUB_PULLED=sha256:old
pass=0
check() { if eval "$2"; then pass=$((pass + 1)); else echo "FAIL: $1" >&2; exit 1; fi; }
reset_calls() { : >"$STUB_LOG"; }

reset_calls
bash "$script" >"$root/out" 2>&1
check 'finds the backend of the ix-lifegather project' "grep -q 'label=com.docker.compose.project=ix-lifegather --filter label=com.docker.compose.service=backend' '$STUB_LOG'"
check 'pulls latest' "grep -q 'pull --quiet $latest' '$STUB_LOG'"
check 'up to date: no redeploy' "! grep -q midclt '$STUB_LOG'"
check 'up to date: no output' "[[ ! -s '$root/out' ]]"

reset_calls
STUB_PULLED=sha256:new LIFEGATHER_HEALTH_URL=http://127.0.0.1:8787/health/ready bash "$script" >"$root/out"
check 'new image: redeploys the app' "grep -q 'midclt call -j app.redeploy lifegather' '$STUB_LOG'"
check 'new image: checks health' "grep -q 'curl .*http://127.0.0.1:8787/health/ready' '$STUB_LOG'"
check 'new image: reports the update' "grep -q \"Updating app 'lifegather' from sha256:old to sha256:new\" '$root/out'"

reset_calls
STUB_PULLED=sha256:new LIFEGATHER_TRUENAS_APP=other bash "$script" >/dev/null
check 'uses the configured app name' "grep -q 'project=ix-other' '$STUB_LOG' && grep -q 'app.redeploy other' '$STUB_LOG'"

reset_calls
if STUB_PULLED=sha256:new STUB_FAIL=health LIFEGATHER_HEALTH_URL=http://127.0.0.1:8787/health/ready \
    bash "$script" >/dev/null 2>"$root/err"; then check 'unhealthy app fails' false; fi
check 'unhealthy app reaches stderr' "grep -q 'did not become healthy' '$root/err'"

reset_calls
STUB_CONTAINER='' bash "$script" >"$root/out" 2>&1
check 'stopped app: nothing pulled' "! grep -q pull '$STUB_LOG'"
check 'stopped app: no redeploy' "! grep -q midclt '$STUB_LOG'"

reset_calls
if STUB_CONFIGURED=ghcr.io/bgoldbeck/life-gather@sha256:pinned bash "$script" 2>"$root/err"; then
    check 'pinned image fails' false
fi
check 'pinned image: nothing pulled' "! grep -q pull '$STUB_LOG'"
check 'pinned image: explains the fix' "grep -q 'change its image to the latest tag' '$root/err'"

reset_calls
if STUB_FAIL=pull bash "$script" 2>"$root/err"; then check 'failed pull fails' false; fi
check 'failed pull: no redeploy' "! grep -q midclt '$STUB_LOG'"
check 'failed pull reaches stderr' "grep -q 'Could not pull' '$root/err'"

reset_calls
if STUB_PULLED=sha256:new STUB_FAIL=app.redeploy bash "$script" >/dev/null 2>"$root/err"; then
    check 'failed redeploy fails' false
fi
check 'failed redeploy reaches stderr' "grep -q 'Redeploying app' '$root/err'"

reset_calls
exec 8>"$LIFEGATHER_LOCK_FILE"
flock 8
STUB_PULLED=sha256:new bash "$script"
check 'a held lock skips the run' "[[ ! -s '$STUB_LOG' ]]"
flock --unlock 8

echo "auto-update.sh: $pass checks passed."
