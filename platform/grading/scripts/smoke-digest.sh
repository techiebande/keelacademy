#!/usr/bin/env bash
# smoke-digest.sh — S4.3 deterministic proof: Proactive retention weekly personalized digest
# (sent whether or not the student logged in), 4 mandatory pillars, deduplication guarantees,
# email transport adapter against fake_email.py, atomic spine events ('digest.generated', 'digest.delivered'),
# and /digest/latest endpoint.
#
# Scratch postgres:16-alpine (0001..0012) seeded with 3 distinct student personas.
#
# Runs:
# - fake Email server (fake_email.py)
# - practice/server.py (with digest endpoints)
# - smoke-digest-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-digest-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
FAKE_EMAIL="$SCRIPT_DIR/../community/fake_email.py"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-digest-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-digest-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-digest-now.XXXXXX.txt)"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

FAKE_EMAIL_PID=""
SERVER_PID=""

cleanup() {
    for pid in "$SERVER_PID" "$FAKE_EMAIL_PID"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-digest-* 2>/dev/null || true
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
FAKE_EMAIL_PORT="$(free_port)"
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

echo "== applying schema 0001..0012 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding 3 distinct student personas (Active, Idle, Route-completed) =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
-- 1. Students
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),   -- Persona 1: Active
    ('bob@keel.test', 'Bob'),       -- Persona 2: Idle (0 attempts/logins this week)
    ('carol@keel.test', 'Carol');   -- Persona 3: Route-completed

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 50000, 1000 FROM students;

-- 2. Enrollments
INSERT INTO enrollments (student_id, unit_id, status)
SELECT id, '1.1', 'active' FROM students;

INSERT INTO enrollments (student_id, unit_id, status)
VALUES ((SELECT id FROM students WHERE display_name = 'Carol'), '12.1', 'active');

-- 3. Pods & Memberships
INSERT INTO pods (name, cohort_week, discord_channel_id)
VALUES ('Pod 2026-W35-Alpha', '2026-W35', 'chan_digest_pod');

INSERT INTO pod_memberships (pod_id, student_id, active)
SELECT (SELECT id FROM pods LIMIT 1), id, true FROM students;

-- Pod post activity
INSERT INTO pod_posts (pod_id, student_id, week_number, shipped_text, broke_text, next_text)
VALUES
    ((SELECT id FROM pods LIMIT 1), (SELECT id FROM students WHERE display_name = 'Alice'), 1, 'Shipped Unit 1.1 extraction parser', 'Broke date parser on ISO timezones', 'Start Unit 1.2 sandbox runner');

-- 4. Persona Specific History
-- Alice (Active): Has completed Unit 1.1, active progress
INSERT INTO progress (student_id, unit_id, state, passed_at)
VALUES ((SELECT id FROM students WHERE display_name = 'Alice'), '1.1', 'passed', clock_timestamp() - interval '2 days');

INSERT INTO practice_attempts (student_id, unit_id, passed, pass_count, total_checks, results_json)
VALUES ((SELECT id FROM students WHERE display_name = 'Alice'), '1.1', true, 5, 5, '[]'::jsonb);

-- Carol (Route-completed): Completed units 1.1, 1.2, 5.1, 12.1
INSERT INTO progress (student_id, unit_id, state, passed_at)
VALUES
    ((SELECT id FROM students WHERE display_name = 'Carol'), '1.1', 'passed', clock_timestamp() - interval '10 days'),
    ((SELECT id FROM students WHERE display_name = 'Carol'), '1.2', 'passed', clock_timestamp() - interval '8 days'),
    ((SELECT id FROM students WHERE display_name = 'Carol'), '5.1', 'passed', clock_timestamp() - interval '5 days'),
    ((SELECT id FROM students WHERE display_name = 'Carol'), '12.1', 'passed', clock_timestamp() - interval '2 days');

-- Rebate pledges
INSERT INTO rebates (student_id, gate_id, unit_id, amount_cents, rebate_pct, status, window_days, window_ends_at, earned_at)
VALUES
    ((SELECT id FROM students WHERE display_name = 'Alice'), 'phase-5-integration', '5.1', 30000, 15.0, 'pending', 30, clock_timestamp() + interval '20 days', NULL),
    ((SELECT id FROM students WHERE display_name = 'Carol'), 'phase-5-integration', '5.1', 30000, 15.0, 'earned', 30, clock_timestamp() + interval '20 days', clock_timestamp() - interval '5 days'),
    ((SELECT id FROM students WHERE display_name = 'Carol'), 'capstone', '12.1', 30000, 15.0, 'earned', 30, clock_timestamp() + interval '20 days', clock_timestamp() - interval '2 days');
" >/dev/null

echo "== starting fake Email server on 127.0.0.1:$FAKE_EMAIL_PORT =="
KEEL_FAKE_EMAIL_PORT="$FAKE_EMAIL_PORT" \
    python3 "$FAKE_EMAIL" >> "$SERVER_LOG" 2>&1 &
FAKE_EMAIL_PID=$!
wait_ready "$FAKE_EMAIL_PID" "$FAKE_EMAIL_PORT" "fake email server"

echo "== starting practice service on 127.0.0.1:$PRACTICE_PORT =="
echo "2026-08-29T16:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_FAKE_EMAIL_URL="http://127.0.0.1:$FAKE_EMAIL_PORT"
export KEEL_EMAIL_API_URL="http://127.0.0.1:$FAKE_EMAIL_PORT"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"
export KEEL_PRACTICE_NOW="2026-08-29T16:00:00+00:00"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice service"

echo "== running weekly retention digest smoke checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-digest-checks.py"

echo "== ALL SMOKE DIGEST CHECKS PASSED =="
