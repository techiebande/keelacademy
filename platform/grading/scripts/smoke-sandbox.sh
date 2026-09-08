#!/usr/bin/env bash
# smoke-sandbox.sh — S1.4 proof harness for the sandbox runner.
# Builds no database; proves each adversarial fixture's containment outcome
# via smoke-sandbox-checks.py. Exits non-zero on any failure. Every sandbox
# container (keel-sbx-*) is removed on every exit path, including timeouts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../sandbox/runner.py"
FIXTURES="$SCRIPT_DIR/../sandbox/fixtures"
IMAGE="python:3.12-alpine"

# Prefer the Linux docker CLI; fall back to Docker Desktop's Windows binary
# when this WSL distro lacks /var/run/docker.sock (same pattern as the
# smoke-schema/intake/worker harnesses).
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

cleanup() {
    # Sweep every leftover sandbox container — ours, and any orphaned by an
    # interrupted earlier run (the runner removes its own in a finally; this
    # is the belt-and-braces net that makes "zero leftovers" hold regardless).
    "$DOCKER" ps -a --format '{{.Names}}' \
        | grep '^keel-sbx-' \
        | xargs -r "$DOCKER" rm -f -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== ensuring $IMAGE is present =="
"$DOCKER" image inspect "$IMAGE" >/dev/null 2>&1 || "$DOCKER" pull "$IMAGE"

echo "== running sandbox containment checks =="
export SANDBOX_DOCKER="$DOCKER" \
       SANDBOX_RUNNER="$RUNNER" \
       SANDBOX_FIXTURES="$FIXTURES"
python3 "$SCRIPT_DIR/smoke-sandbox-checks.py"

echo
echo "== leftover-container sweep: any 'keel-sbx-*' containers left? =="
leftovers="$("$DOCKER" ps -a --format '{{.Names}}' | grep '^keel-sbx-' || true)"
if [ -n "$leftovers" ]; then
    echo "FAIL: leftover containers found:"
    echo "$leftovers"
    exit 1
fi
echo "(none)"
"$DOCKER" ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

echo "== ALL CHECKS PASSED =="
