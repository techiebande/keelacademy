#!/usr/bin/env bash
# smoke-worker.sh — S1.3 proof harness for the job queue worker.
# Spins up a scratch postgres:16-alpine (0001 + 0002 applied), seeds a student,
# and runs the four proof checks (a)-(d) via smoke-worker-checks.py.
# Exits non-zero on any failure; container and any workers are always removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
WORKER="$SCRIPT_DIR/../worker.py"
IMAGE="postgres:16-alpine"
CONTAINER="keel-worker-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""

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
    if [ -n "$DB_PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Pick a random free host port (same pattern as smoke-schema.sh and smoke-intake.sh).
DB_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"

echo "== starting $IMAGE on 127.0.0.1:$DB_PORT =="
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    "$IMAGE" >/dev/null

# Readiness: a real `select 1` (pg_isready lies during postgres's init restart).
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

echo "== applying schema 0001 + 0002 =="
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/0001_init.sql"
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/0002_intake.sql"

echo "== seeding student =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "INSERT INTO students (email, display_name) VALUES ('alice@keel.test', 'Alice');"

echo "== running worker smoke checks =="
export WORKER_DOCKER="$DOCKER" \
       WORKER_CONTAINER="$CONTAINER" \
       WORKER_DB_USER="$DB_USER" \
       WORKER_DB_NAME="$DB_NAME" \
       WORKER_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
       WORKER_SCRIPT="$WORKER"

python3 "$SCRIPT_DIR/smoke-worker-checks.py"

echo "== ALL CHECKS PASSED =="
