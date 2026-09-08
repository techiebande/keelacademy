#!/usr/bin/env bash
# smoke-c1a.sh — Milestone C1a verification proof
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-c1a-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PROXY_SERVER="$SCRIPT_DIR/../proxy/server.py"
FAKE_UPSTREAM="$SCRIPT_DIR/../practice/fake_judge_upstream.py"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-c1a-token-$$"
TRACE_LOG="$(mktemp /tmp/keel-c1a-trace.XXXXXX.jsonl)"
SERVER_LOG="$(mktemp /tmp/keel-c1a-servers.XXXXXX.log)"

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
    rm -f "$TRACE_LOG" "$SERVER_LOG" /tmp/keel-c1a-* 2>/dev/null || true
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
        if python3 -c "import socket, sys; s=socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=1); s.close()" "$port" 2>/dev/null; then
            return 0
        fi
        if [ "$i" -eq 60 ]; then
            echo "FAIL: $name never became ready on port $port" >&2
            exit 1
        fi
        sleep 0.5
    done
}

echo "=== Milestone C1a: Phase 0 Authoring & Conceptual Unit Proof ==="

# Step 1: Content schema validation
echo "[1/6] Validating content schemas, rubrics, routing, maps, and diagnostics..."
(cd "$REPO_ROOT" && python3 content/tools/validate.py)
(cd "$REPO_ROOT" && python3 content/tools/validate-rubrics.py)
(cd "$REPO_ROOT" && python3 content/tools/validate-routing.py)
(cd "$REPO_ROOT" && python3 content/tools/validate-map.py)
(cd "$REPO_ROOT" && python3 content/tools/validate-diagnostics.py)

# Step 2: Spin up Postgres
DB_PORT="$(free_port)"
FAKE_PORT="$(free_port)"
PROXY_PORT="$(free_port)"
PRACTICE_PORT="$(free_port)"

echo "[2/6] Starting Postgres container ($CONTAINER) on port $DB_PORT..."
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

# Step 3: Run migrations 0001..0014
echo "[3/6] Applying Postgres migrations 0001..0014..."
for mig in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery 0014_simulations; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$mig.sql" >/dev/null
done

# Step 4: Seed test students, enrollments, and budgets
echo "[4/6] Seeding test students and enrollments..."
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('bob@keel.test', 'Bob'),
    ('carol@keel.test', 'Carol'),
    ('dave@keel.test', 'Dave');

INSERT INTO enrollments (student_id, unit_id, status)
SELECT id, '0.2', 'active' FROM students WHERE email IN ('alice@keel.test', 'bob@keel.test', 'dave@keel.test');

INSERT INTO enrollments (student_id, unit_id, status)
SELECT id, '0.3', 'active' FROM students WHERE email IN ('alice@keel.test');

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, cap, used FROM (VALUES
    ('alice@keel.test', 100000, 0),
    ('bob@keel.test', 50000, 0),
    ('carol@keel.test', 50000, 0),
    ('dave@keel.test', 100, 100)
) AS s(email, cap, used) JOIN students ON students.email = s.email;
" >/dev/null

export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_CONTENT_ROOT="$REPO_ROOT/content"

# Step 5: Start fake upstream, proxy, and practice server
echo "[5/6] Launching test services (fake upstream :$FAKE_PORT, proxy :$PROXY_PORT, practice :$PRACTICE_PORT)..."
KEEL_FAKE_PORT="$FAKE_PORT" \
    python3 "$FAKE_UPSTREAM" >> "$SERVER_LOG" 2>&1 &
FAKE_PID=$!
wait_ready "$FAKE_PID" "$FAKE_PORT" "fake OpenAI upstream"

KEEL_PROXY_PORT="$PROXY_PORT" \
KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$FAKE_PORT/v1" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$PROXY_SERVER" >> "$SERVER_LOG" 2>&1 &
PROXY_PID=$!
wait_ready "$PROXY_PID" "$PROXY_PORT" "proxy server"

export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_PROXY_URL="http://127.0.0.1:$PROXY_PORT"
export KEEL_TRACE_LOG="$TRACE_LOG"
export KEEL_SANDBOX_IMAGE="keel-runner:0.1"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice server"

# Step 6: Run automated check suite
echo "[6/6] Executing smoke-c1a automated assertion tests..."
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
export KEEL_FAKE_URL="http://127.0.0.1:$FAKE_PORT"
python3 "$SCRIPT_DIR/smoke-c1a-checks.py" \
    --practice-url "http://127.0.0.1:$PRACTICE_PORT" \
    --fake-url "http://127.0.0.1:$FAKE_PORT" \
    --app-token "$APP_TOKEN" \
    --trace-log "$TRACE_LOG"

echo "PASS: All Milestone C1a verification checks succeeded!"
