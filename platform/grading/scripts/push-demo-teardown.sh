#!/usr/bin/env bash
# push-demo-teardown.sh — S1.9 Part B cleanup: stop every daemon started by
# push-demo-setup.sh and remove every /tmp artifact of the demo. Every
# removal is verified (the tooling-hazard rule); a nonzero exit means
# something survived — chase it before declaring the demo over.
set -u

ROOT="/tmp/keel-push-demo"
FAIL=0

if [ ! -e "$ROOT" ]; then
    echo "nothing to tear down ($ROOT does not exist)"
    exit 0
fi

# Prefer the Linux docker CLI; fall back to Docker Desktop's Windows binary.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    DOCKER=""
fi

echo "== stopping daemons =="
if [ -f "$ROOT/pids.env" ]; then
    # shellcheck disable=SC1090
    . "$ROOT/pids.env"
    for pid in ${INTAKE_PID:-} ${PROXY_PID:-} ${WORKER_PID:-}; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for i in $(seq 1 20); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.2
            done
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
fi

if [ -n "$DOCKER" ]; then
    echo "== removing containers =="
    # The worker spawns one sandbox container per layer-1 check; sweep any
    # stragglers, then the demo's postgres.
    "$DOCKER" ps -a --format '{{.Names}}' | grep -E '^keel-(sbx|grader|push-demo)-' \
        | xargs -r "$DOCKER" rm -f -v >/dev/null 2>&1 || true
fi

echo "== removing scratch root =="
rm -rf "$ROOT"
rm -rf /tmp/keel-layer1-* /tmp/keel-verdict-* 2>/dev/null || true

echo "== verifying =="
if [ -e "$ROOT" ]; then
    echo "FAIL: $ROOT survived removal" >&2
    FAIL=1
else
    echo "PASS: $ROOT gone"
fi
LEFT="$(ls -d /tmp/keel-push-demo /tmp/keel-layer1-* /tmp/keel-verdict-* 2>/dev/null | wc -l)"
if [ "$LEFT" -ne 0 ]; then
    echo "FAIL: keel scratch artifacts remain under /tmp:" >&2
    ls -d /tmp/keel-push-demo /tmp/keel-layer1-* /tmp/keel-verdict-* 2>/dev/null >&2
    FAIL=1
else
    echo "PASS: no /tmp/keel-push-demo, /tmp/keel-layer1-*, /tmp/keel-verdict-* remain"
fi
if [ -n "$DOCKER" ]; then
    KEEL_CONTAINERS="$("$DOCKER" ps -a --format '{{.Names}}' | grep -c '^keel-' || true)"
    if [ "${KEEL_CONTAINERS:-0}" != "0" ]; then
        echo "FAIL: keel-* containers remain:" >&2
        "$DOCKER" ps -a --format '{{.Names}}' | grep '^keel-' >&2
        FAIL=1
    else
        echo "PASS: zero keel-* containers"
    fi
fi

exit "$FAIL"
