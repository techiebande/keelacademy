#!/usr/bin/env bash
# smoke-skeptical-sim.sh — S4.6 deterministic proof: Simulation service skeptical-reviewer personas,
# technical stakeholder (Marcus Vance), business owner (Elena Rostova), scored defenses,
# multi-turn dialogue state persistence, behavioral pushback against hand-wavy claims and technical jargon,
# evaluation judge scoring against Section 14.3 / 14.4 rubrics,
# defense clearance gate check, atomic gate.defense_cleared spine event emission,
# and defense status endpoints (GET /students/<id>/simulations/defenses).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-skeptical-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-skeptical-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-skep-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-skep-now.XXXXXX.txt)"

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
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-skep-* 2>/dev/null || true
    find "$SCRIPT_DIR/.." -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

free_port() {
    python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()"
}

wait_ready() {
    local pid="$1" port="$2" name="$3"
    for i in $(seq 1 60); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "FAIL: $name died at startup:" >&2
            cat "$SERVER_LOG" >&2 || true
            return 1
        fi
        if python3 -c "import socket, sys; s = socket.socket(); s.connect(('127.0.0.1', int(sys.argv[1]))); s.close()" "$port" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    echo "FAIL: $name did not listen on :$port within 6s" >&2
    cat "$SERVER_LOG" >&2 || true
    return 1
}

echo "=== S4.6 SKEPTICAL REVIEWER SIMULATION & DEFENSE GATES SMOKE TEST ==="

echo "--- Step 1: Content Schema & Persona Validation ---"
python3 "$REPO_ROOT/content/tools/validate.py"

echo "--- Step 2: Spin up isolated PostgreSQL test container ---"
DB_PORT="$(free_port)"
PRACTICE_PORT="$(free_port)"

"$DOCKER" run -d --name "$CONTAINER"     -e POSTGRES_USER="$DB_USER"     -e POSTGRES_PASSWORD=smoke     -e POSTGRES_DB="$DB_NAME"     -p "127.0.0.1:$DB_PORT:5432"     "$IMAGE" >/dev/null

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

echo "Applying schemas (0001..0014)..."
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery 0014_simulations; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

# Seed mock test students
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "
INSERT INTO students (id, email, display_name) VALUES
    (101, 'alex.tech@example.com', 'Alex Tech'),
    (102, 'jordan.biz@example.com', 'Jordan Biz'),
    (103, 'casey.fail@example.com', 'Casey Fail');

SELECT setval('students_id_seq', 200);
" >/dev/null

echo "--- Step 3: Launch Practice Server with Simulation Engine ---"
echo "2026-08-29T16:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"
export KEEL_PRACTICE_NOW="2026-08-29T16:00:00+00:00"
export KEEL_SIMULATION_MOCK="1"
export KEEL_CONTENT_ROOT="$REPO_ROOT/content"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice-server"

echo "--- Step 4: Execute Deterministic Skeptical Reviewer Checks ---"
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-skeptical-sim-checks.py"

echo "=== S4.6 SKEPTICAL REVIEWER SIMULATION SMOKE SUITE PASSED ==="
