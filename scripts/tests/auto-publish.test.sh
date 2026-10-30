#!/usr/bin/env bash
# Offline checks for auto-publish.sh: a local bare repository stands in for
# GitHub, and stub docker/midclt commands record calls, so nothing is built,
# uploaded or redeployed. Run: bash scripts/tests/auto-publish.test.sh
set -euo pipefail

source_script=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/auto-publish.sh
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
export HOME=$root/home GIT_CONFIG_NOSYSTEM=1
mkdir -p "$HOME" "$root/bin"
git config --global user.email test@example.invalid
git config --global user.name Test
git config --global init.defaultBranch main

# Stub docker: log each call; STUB_FAIL makes a matching call fail.
cat >"$root/bin/docker" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_LOG"
[[ -n ${STUB_FAIL:-} && "$*" == *"$STUB_FAIL"* ]] && exit 1
case "$*" in
    'info --format {{.OSType}}') echo linux ;;
    'inspect --format {{.State.Health.Status}} '*) echo healthy ;;
    'image inspect --format {{.Size}} '*) echo 123 ;;
    'build --quiet --tag '*' -'|'exec --interactive '*) cat >/dev/null ;;
    *' login ghcr.io '*) cat >"$STUB_LOG.token" ;;
    # A tag "exists" when $STUB_REGISTRY has a file named after it.
    *' manifest inspect ghcr.io/bgoldbeck/life-gather:'*)
        args=$*
        tag=${args##*:}
        [[ -f $STUB_REGISTRY/$tag ]] || exit 1
        cat -- "$STUB_REGISTRY/$tag" ;;
esac
SH
cat >"$root/bin/midclt" <<'SH'
#!/usr/bin/env bash
printf 'midclt %s\n' "$*" >>"$STUB_LOG"
SH
chmod +x "$root/bin/docker" "$root/bin/midclt"
export PATH=$root/bin:$PATH

git init --quiet --bare "$root/origin.git"
git clone --quiet "$root/origin.git" "$root/seed" 2>/dev/null
mkdir -p "$root/seed/backend/src/lifegather" "$root/seed/scripts"
echo '__version__ = "1.2.3"' >"$root/seed/backend/src/lifegather/version.py"
echo 'COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/' >"$root/seed/Dockerfile"
cp "$source_script" "$root/seed/scripts/auto-publish.sh"
git -C "$root/seed" add . && git -C "$root/seed" commit --quiet -m one && git -C "$root/seed" push --quiet origin main
git clone --quiet "$root/origin.git" "$root/nas/source"
# Like a clone made over SSH or with a credential helper: cron must not use it.
git -C "$root/nas/source" remote set-url origin git@unreachable.invalid:life-gather.git
export LIFEGATHER_SOURCE_URL=$root/origin.git

export LIFEGATHER_AUTOBUILD_DIR=$root/nas/state STUB_LOG=$root/calls STUB_REGISTRY=$root/registry
mkdir -p "$LIFEGATHER_AUTOBUILD_DIR/docker-config" "$STUB_REGISTRY"
script=$root/nas/source/scripts/auto-publish.sh
pass=0
check() { if eval "$2"; then pass=$((pass + 1)); else echo "FAIL: $1" >&2; exit 1; fi; }
reset_calls() { : >"$STUB_LOG"; }
commit() {
    echo "$1" >"$root/seed/change.txt"
    git -C "$root/seed" add . && git -C "$root/seed" commit --quiet -m "$1" && git -C "$root/seed" push --quiet origin main
    git -C "$root/seed" rev-parse HEAD
}

reset_calls
if bash "$script" 2>"$root/err"; then check 'missing login fails' false; fi
check 'missing login stops before building' "! grep -q '^build' '$STUB_LOG'"
check 'missing login is not recorded as a failed commit' "[[ ! -f $LIFEGATHER_AUTOBUILD_DIR/last-failed-revision ]]"
check 'failure reaches stderr' "grep -q 'auto-publish failed' '$root/err'"

echo '{"auths":{"ghcr.io":{}}}' >"$LIFEGATHER_AUTOBUILD_DIR/docker-config/config.json"
second=$(commit two)
reset_calls
LIFEGATHER_TRUENAS_APP=lifegather bash "$script"
check 'fast-forwards to GitHub main' "[[ \$(git -C '$root/nas/source' rev-parse HEAD) == $second ]]"
check 'runs backend tests' "grep -q 'uv run --locked pytest' '$STUB_LOG'"
check 'runs frontend checks' "grep -q 'npm test' '$STUB_LOG'"
check 'pushes the commit tag' "grep -q 'push --quiet ghcr.io/bgoldbeck/life-gather:sha-$second' '$STUB_LOG'"
check 'pushes latest' "grep -q 'push --quiet ghcr.io/bgoldbeck/life-gather:latest' '$STUB_LOG'"
check 'uses the private registry login' "grep -q -- '--config $LIFEGATHER_AUTOBUILD_DIR/docker-config push' '$STUB_LOG'"
check 'redeploys the TrueNAS app' "grep -q 'midclt call -j app.redeploy lifegather' '$STUB_LOG'"
check 'records the published commit' "[[ \$(cat '$LIFEGATHER_AUTOBUILD_DIR/last-published-revision') == $second ]]"
check 'removes test containers' "grep -q '^rm --force --volumes lifegather-autobuild-' '$STUB_LOG'"

reset_calls
bash "$script" >"$root/out" 2>&1
check 'up to date: no docker calls' "[[ ! -s '$STUB_LOG' ]]"
check 'up to date: no output' "[[ ! -s '$root/out' ]]"

third=$(commit three)
reset_calls
if STUB_FAIL='npm test' bash "$script" 2>/dev/null; then check 'failed check fails the run' false; fi
check 'failed check: nothing pushed' "! grep -q 'push' '$STUB_LOG'"
check 'failed check: no redeploy' "! grep -q midclt '$STUB_LOG'"
check 'failed check: commit recorded' "[[ \$(cat '$LIFEGATHER_AUTOBUILD_DIR/last-failed-revision') == $third ]]"
reset_calls
bash "$script"
check 'failed commit is not rebuilt' "[[ ! -s '$STUB_LOG' ]]"
touch -d '7 hours ago' "$LIFEGATHER_AUTOBUILD_DIR/last-failed-revision"
STUB_FAIL='npm test' bash "$script" 2>/dev/null || true
check 'a failed commit is retried after six hours' "grep -q 'npm test' '$STUB_LOG'"
reset_calls
bash "$script" --force
check '--force retries it' "grep -q 'push --quiet ghcr.io/bgoldbeck/life-gather:sha-$third' '$STUB_LOG'"
check 'success clears the failure' "[[ ! -f $LIFEGATHER_AUTOBUILD_DIR/last-failed-revision ]]"
check 'previous build is untagged' "grep -q 'image rm ghcr.io/bgoldbeck/life-gather:sha-$second' '$STUB_LOG'"

commit four >/dev/null
reset_calls
exec 8>"$LIFEGATHER_AUTOBUILD_DIR/auto-publish.lock"
flock 8
bash "$script"
check 'a held lock skips the run' "[[ ! -s '$STUB_LOG' ]]"
flock --unlock 8

echo dirty >"$root/nas/source/local.txt"
if bash "$script" 2>/dev/null; then check 'dirty clone fails' false; fi
check 'dirty clone: nothing built' "! grep -q '^build' '$STUB_LOG'"
rm "$root/nas/source/local.txt"

# Token file instead of a saved docker login.
rm "$LIFEGATHER_AUTOBUILD_DIR/docker-config/config.json"
fifth=$(commit five)
reset_calls
printf 'test-token\n' >"$LIFEGATHER_AUTOBUILD_DIR/ghcr-token"
chmod 644 "$LIFEGATHER_AUTOBUILD_DIR/ghcr-token"
if bash "$script" 2>/dev/null; then check 'a readable token file fails' false; fi
check 'a readable token file stops before building' "! grep -q '^build' '$STUB_LOG'"
chmod 600 "$LIFEGATHER_AUTOBUILD_DIR/ghcr-token"
reset_calls
bash "$script" --force
check 'logs in with the token file' "grep -q 'login ghcr.io --username bgoldbeck --password-stdin' '$STUB_LOG'"
check 'passes the token on stdin only' "[[ \$(cat '$STUB_LOG.token') == test-token ]] && ! grep -q test-token '$STUB_LOG' '$LIFEGATHER_AUTOBUILD_DIR/auto-publish.log'"
check 'pushes with the per-run login' "grep -q -- '--config $LIFEGATHER_AUTOBUILD_DIR/registry\..* push --quiet ghcr.io/bgoldbeck/life-gather:sha-$fifth' '$STUB_LOG'"
check 'removes the per-run login' "! compgen -G '$LIFEGATHER_AUTOBUILD_DIR/registry.*' >/dev/null"
reset_calls
if STUB_FAIL='login ghcr.io' bash "$script" --force 2>/dev/null; then check 'a rejected token fails' false; fi
check 'a rejected token stops before building' "! grep -q '^build' '$STUB_LOG'"

# Another machine (the Windows scheduled publisher) already uploaded main.
rm -f "$LIFEGATHER_AUTOBUILD_DIR/last-failed-revision"
sixth=$(commit six)
echo 'digest-six' >"$STUB_REGISTRY/sha-$sixth"
echo 'digest-five' >"$STUB_REGISTRY/latest"
reset_calls
bash "$script"
check 'latest not moved yet: nothing built' "! grep -q '^build' '$STUB_LOG'"
check 'latest not moved yet: not recorded' "[[ \$(cat '$LIFEGATHER_AUTOBUILD_DIR/last-published-revision') != $sixth ]]"
echo 'digest-six' >"$STUB_REGISTRY/latest"
reset_calls
LIFEGATHER_TRUENAS_APP=lifegather bash "$script"
check 'published elsewhere: nothing built' "! grep -q '^build' '$STUB_LOG'"
check 'published elsewhere: nothing pushed' "! grep -q ' push ' '$STUB_LOG'"
check 'published elsewhere: recorded' "[[ \$(cat '$LIFEGATHER_AUTOBUILD_DIR/last-published-revision') == $sixth ]]"
check 'published elsewhere: redeploys' "grep -q 'midclt call -j app.redeploy lifegather' '$STUB_LOG'"

# Uploaded elsewhere while this run was building: keep that image.
seventh=$(commit seven)
reset_calls
cat >"$root/bin/npm-race" <<SH
#!/usr/bin/env bash
echo digest-seven-windows >'$STUB_REGISTRY/sha-$seventh'
SH
chmod +x "$root/bin/npm-race"
sed -i 's|^case "\$\*" in$|[[ "$*" == *"npm test"* ]] \&\& npm-race\ncase "$*" in|' "$root/bin/docker"
bash "$script"
check 'race: built and tested' "grep -q 'npm test' '$STUB_LOG'"
check 'race: commit tag not overwritten' "! grep -q 'push --quiet ghcr.io/bgoldbeck/life-gather:sha-$seventh' '$STUB_LOG'"
check 'race: recorded as published' "[[ \$(cat '$LIFEGATHER_AUTOBUILD_DIR/last-published-revision') == $seventh ]]"

echo "auto-publish.sh: $pass checks passed."
