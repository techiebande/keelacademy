#!/usr/bin/env bash
# smoke-gates.sh — S2.7 deterministic proof: the gate engine turning verdict
# events into unlock state and the published gate event contract, fully
# offline, including the real rebate machine earning from engine-emitted
# events.
#
# Scratch postgres:16-alpine (0001..0006) seeded with four students; alice
# and bob carry an active enrollment, carol does not. The checks in
# smoke-gates-checks.py fabricate the UPSTREAM events (enrollment.activated
# and verdict.issued, byte-shaped exactly as enroll/server.py and worker.py
# write them — the offline deterministic fake for the verdict pipeline) and
# run the engine one-shot at deterministic clock points (KEEL_GATE_NOW) and
# the rebate machine one-shot at matching points (KEEL_REBATE_NOW): pass
# unlocks, fail does not unlock, replay is a no-op, unenrolled and no-rule
# verdicts are refused, unlocks never reverse, the enrollment->pledge and
# verdict->passage->earn chain runs end to end, and the KEEL_CONTENT_ROOT
# lever lets a scratch rule set gate any unit. No servers, no sleeps, no
# network beyond the postgres pull. Exits non-zero on any failure; the
# container is always removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-gates-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"

# Deterministic ledger economics for the chain proofs: $100 default price,
# 15% rebate, 60-day window for engine-emitted pledges (which carry no
# window_days; the machine's configured default applies).
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

echo "== running gate engine checks =="
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$SCRIPT_DIR/smoke-gates-checks.py"

echo "== ALL CHECKS PASSED =="
