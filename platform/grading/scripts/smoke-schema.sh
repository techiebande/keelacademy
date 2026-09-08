#!/usr/bin/env bash
# smoke-schema.sh — apply 0001_init.sql to a scratch postgres:16-alpine and
# run the proof checks in smoke.sql. Exits non-zero on any failure; the
# container is always removed via an EXIT trap.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA="$SCRIPT_DIR/../schema/0001_init.sql"
SMOKE="$SCRIPT_DIR/smoke.sql"
IMAGE="postgres:16-alpine"
CONTAINER="keel-grading-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PORT=""

# Prefer the Linux docker CLI; fall back to Docker Desktop's Windows binary
# when this WSL distro lacks /var/run/docker.sock.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

cleanup() {
    if [ -n "$PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Pick a random free host port.
PORT="$(python3 - <<'EOF'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
EOF
)"

echo "== starting $IMAGE on 127.0.0.1:$PORT =="
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$PORT:5432" \
    "$IMAGE" >/dev/null

# Wait for readiness. pg_isready alone reports ready during the init
# restart, so require a real query to succeed.
for i in $(seq 1 60); do
    if "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select 1;" >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "FAIL: postgres never became ready" >&2
        exit 1
    fi
    sleep 1
done

echo "== version banner =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select version();"

echo "== applying schema/0001_init.sql =="
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA"

echo "== running smoke checks =="
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SMOKE"

echo "== ALL CHECKS PASSED =="
