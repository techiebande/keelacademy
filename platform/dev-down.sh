#!/usr/bin/env bash
# platform/dev-down.sh — Stop all Keel Academy background services and remove dev container.
set -euo pipefail

LOG_DIR="/tmp/keel-dev-logs"
STATE_FILE="$LOG_DIR/pids.env"
CONTAINER="keel-dev-pg"

echo "== Stopping background microservices =="
if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    for pid in "${APP_PID:-}" "${FAKE_STRIPE_PID:-}" "${FAKE_PADDLE_PID:-}" "${FAKE_JUDGE_PID:-}" "${PROXY_PID:-}" "${ENROLL_PID:-}" "${READER_PID:-}" "${PRACTICE_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    rm -f "$STATE_FILE"
fi

for p in 8790 8791 8792 8793 8794 8795 8798; do
    fuser -k -n tcp "$p" 2>/dev/null || true
done

echo "== Stopping Postgres container =="
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
fi

echo "== Dev environment stopped =="
