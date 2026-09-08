#!/usr/bin/env bash
# smoke-map.sh — S2.8 deterministic proof of progress dashboard map v1.
#
# Scratch postgres:16-alpine (0001..0006) seeded with four students.
# Checks in smoke-map-checks.py test:
#   1. map skeleton validation & content-as-data integrity (13 phases 0..12)
#   2. not-authored honesty (unauthored units render as planned/content arriving)
#   3. enrollment activation & baseline available states
#   4. queued and grading mid-flight submission states
#   5. pass lights up the track through Phase 5 integration gate
#   6. fail does not unlock or earn rebate
#   7. unlocks never reverse on late fail
#   8. replay & idempotency: cursor reset leaves map state identical
#   9. unenrolled signed-in student (Carol) pre-payment honesty
#  10. reader endpoint SELECT-only /students/<id>/submissions
#
# Exits non-zero on any failure; container is always cleaned up via EXIT trap.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-map-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"

export KEEL_PRICE_CENTS_DEFAULT="10000"
export KEEL_REBATE_PCT="15"
export KEEL_REBATE_WINDOW_DAYS="60"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

cleanup() {
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    find "$SCRIPT_DIR/.." -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

DB_PORT="$(free_port)"

echo "== starting $IMAGE on 127.0.0.1:$DB_PORT =="
"$DOCKER" run -d --name "$CONTAINER"     -e POSTGRES_USER="$DB_USER"     -e POSTGRES_PASSWORD=smoke     -e POSTGRES_DB="$DB_NAME"     -p "127.0.0.1:$DB_PORT:5432"     "$IMAGE" >/dev/null

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

echo "== applying schema 0001..0006 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding alice, bob, carol, dave =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('bob@keel.test', 'Bob'),
    ('carol@keel.test', 'Carol'),
    ('dave@keel.test', 'Dave');" >/dev/null

echo "== running map smoke checks =="
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"     python3 "$SCRIPT_DIR/smoke-map-checks.py"

echo "== ALL MAP SMOKE CHECKS PASSED =="
