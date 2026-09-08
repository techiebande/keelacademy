#!/usr/bin/env bash
# smoke-concierge.sh — S3.5 deterministic proof: concierge v1 with
# server-side teach/guard mode switch derived from adaptive route state,
# budget enforcement, anti-injection prompt defense, and atomic persistence.
#
# Scratch postgres:16-alpine (0001..0009) seeded with:
# - alice: active enrollment for unit 3.2.1, budget cap 50000 (0 used)
# - bob:   active enrollment for unit 3.2.1, budget cap 50000 (0 used)
# - carol: unenrolled, budget cap 50000 (0 used)
# - dave:  active enrollment for unit 3.2.1, budget cap 100 (100 used -> exhausted)
#
# Runs:
# - fake OpenAI judge upstream
# - proxy/server.py
# - practice/server.py (KEEL_PRACTICE_NOW_FILE clock knob)
# - smoke-concierge-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-concierge-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PROXY_SERVER="$SCRIPT_DIR/../proxy/server.py"
FAKE_UPSTREAM="$SCRIPT_DIR/../practice/fake_judge_upstream.py"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-concierge-token-$$"
TRACE_LOG="$(mktemp /tmp/keel-concierge-trace.XXXXXX.jsonl)"
SERVER_LOG="$(mktemp /tmp/keel-concierge-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-concierge-now.XXXXXX.txt)"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

FAKE_PID=""
PROXY_PID=""
SERVER_PID=""

cleanup() {
    for pid in "$SERVER_PID" "$PROXY_PID" "$FAKE_PID"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -f "$TRACE_LOG" "$SERVER_LOG" "$NOW_FILE" /tmp/keel-concierge-* 2>/dev/null || true
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

DB_PORT="$(free_port)"
FAKE_PORT="$(free_port)"
PROXY_PORT="$(free_port)"
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

echo "== applying schema 0001..0009 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding alice, bob, carol, dave, enrollments and budgets =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('bob@keel.test', 'Bob'),
    ('carol@keel.test', 'Carol'),
    ('dave@keel.test', 'Dave');

INSERT INTO enrollments (student_id, unit_id, status)
SELECT id, '3.2.1', 'active' FROM students WHERE email IN ('alice@keel.test', 'bob@keel.test', 'dave@keel.test');

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 50000, 0 FROM students WHERE email IN ('alice@keel.test', 'bob@keel.test', 'carol@keel.test');

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 100, 100 FROM students WHERE email = 'dave@keel.test';
" >/dev/null

echo "== starting fake judge upstream on 127.0.0.1:$FAKE_PORT =="
KEEL_FAKE_PORT="$FAKE_PORT" \
KEEL_FAKE_PROMPT_TOKENS=800 \
KEEL_FAKE_COMPLETION_TOKENS=200 \
    python3 "$FAKE_UPSTREAM" >> "$SERVER_LOG" 2>&1 &
FAKE_PID=$!
wait_ready "$FAKE_PID" "$FAKE_PORT" "fake judge upstream"

echo "== starting LLM proxy on 127.0.0.1:$PROXY_PORT =="
KEEL_PROXY_PORT="$PROXY_PORT" \
KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$FAKE_PORT/v1" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$PROXY_SERVER" >> "$SERVER_LOG" 2>&1 &
PROXY_PID=$!
wait_ready "$PROXY_PID" "$PROXY_PORT" "proxy"

echo "== starting practice grading service on 127.0.0.1:$PRACTICE_PORT (deterministic clock file) =="
echo "2026-03-01T09:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_PROXY_URL="http://127.0.0.1:$PROXY_PORT"
export KEEL_TRACE_LOG="$TRACE_LOG"
export KEEL_SANDBOX_IMAGE="keel-runner:0.1"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice service"

echo "== running concierge checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
export KEEL_FAKE_URL="http://127.0.0.1:$FAKE_PORT"
export KEEL_CONCIERGE_NOW_FILE="$NOW_FILE"
python3 "$SCRIPT_DIR/smoke-concierge-checks.py"

echo "== ALL SMOKE CONCIERGE CHECKS PASSED =="
