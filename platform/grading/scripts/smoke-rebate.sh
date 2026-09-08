#!/usr/bin/env bash
# smoke-rebate.sh — S2.6 deterministic proof: the rebate state machine wired
# to gate events, fully offline.
#
# Scratch postgres:16-alpine (0001..0005) seeded with four students, price
# $100, rebate 15%, default window 60 days. The checks in
# smoke-rebate-checks.py fabricate the gate.pledged / gate.passed events S2.7
# will emit (same events spine the verdict pipeline writes) and run the
# machine one-shot under a deterministic clock (KEEL_REBATE_NOW): earn-once,
# replayed gate events, out-of-window expiry, wrong-unit rejection, unknown
# gate/student, runbook marks that never move backwards, cursor-reset replay
# safety, and ledger auditability. No servers, no sleeps, no network beyond
# the postgres pull. Exits non-zero on any failure; the container is always
# removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-rebate-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"

# Deterministic ledger economics: $100 price, 15% rebate (architecture band
# 15-20), 60-day default window for pledges that do not carry one.
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
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    "$IMAGE" >/dev/null

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

echo "== applying schema 0001..0005 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding alice, bob, carol, dave =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('bob@keel.test', 'Bob'),
    ('carol@keel.test', 'Carol'),
    ('dave@keel.test', 'Dave');" >/dev/null

echo "== running rebate machine checks =="
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$SCRIPT_DIR/smoke-rebate-checks.py"

echo "== ALL CHECKS PASSED =="
