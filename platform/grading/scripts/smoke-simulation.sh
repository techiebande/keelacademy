#!/usr/bin/env bash
# smoke-simulation.sh — S4.5 deterministic proof: Business Simulation Engine,
# discovery-call practice persona (Sarah Jenkins at OmniCart Operations),
# multi-turn dialogue state persistence, behavioral pushback against premature pitching,
# evaluation judge scoring against the 11.5.1 discovery checklist,
# atomic spine events ('simulation.started', 'simulation.turn_completed', 'simulation.scored'),
# and strict auth/ownership boundaries.
#
# Scratch postgres:16-alpine (0001..0014) seeded with students.
#
# Runs:
# - content/tools/validate.py
# - practice/server.py (with simulation engine)
# - smoke-simulation-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-simulation-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-simulation-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-sim-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-sim-now.XXXXXX.txt)"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-sim-* 2>/dev/null || true
    find "$SCRIPT_DIR/.." -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

wait_ready() {
    local pid="$1" port="$2" name="$3"
    for i in $(seq 1 60); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "FAIL: $name died at startup:" >&2
            cat "$SERVER_LOG" >&2 || true
            exit 1
        fi
        if python3 - "$port" <<'PYEOF' 2>/dev/null
import socket, sys
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=1)
s.close()
PYEOF
        then
            return 0
        fi
        if [ "$i" -eq 60 ]; then
            echo "FAIL: $name never became ready on port $port" >&2
            exit 1
        fi
        sleep 0.5
    done
}

echo "== 1. Validating Content Schemas =="
python3 "$REPO_ROOT/content/tools/validate.py"

DB_PORT="$(free_port)"
PRACTICE_PORT="$(free_port)"

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
    sleep 0.5
done

echo "== applying schema 0001..0014 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery 0014_simulations; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding test students =="
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "
-- Students
INSERT INTO students (id, email, display_name) VALUES
    (1, 'alice@example.com', 'Alice Smith'),
    (2, 'bob@example.com', 'Bob Jones'),
    (3, 'carol@example.com', 'Carol White');

SELECT setval('students_id_seq', 10);
" >/dev/null

echo "== starting practice & simulation service on 127.0.0.1:$PRACTICE_PORT =="
echo "2026-08-29T16:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"
export KEEL_PRACTICE_NOW="2026-08-29T16:00:00+00:00"
export KEEL_SIMULATION_MOCK="1"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice service"

echo "== running simulation smoke checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-simulation-checks.py"

echo "== ALL SMOKE SIMULATION CHECKS PASSED =="
