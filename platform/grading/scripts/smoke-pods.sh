#!/usr/bin/env bash
# smoke-pods.sh — S4.2 deterministic proof: Pod allocation (6–10 capacity),
# weekly post flow (3 mandatory pillars: shipped, broke, next), and Discord
# webhook relay integration against fake_discord.py.
#
# Scratch postgres:16-alpine (0001..0011) seeded with 15 students.
#
# Runs:
# - fake Discord upstream (fake_discord.py)
# - practice/server.py (with pod endpoints)
# - smoke-pods-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-pods-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
FAKE_DISCORD="$SCRIPT_DIR/../community/fake_discord.py"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-pods-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-pods-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-pods-now.XXXXXX.txt)"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

FAKE_DISCORD_PID=""
SERVER_PID=""

cleanup() {
    for pid in "$SERVER_PID" "$FAKE_DISCORD_PID"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-pods-* 2>/dev/null || true
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
FAKE_DISCORD_PORT="$(free_port)"
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

echo "== applying schema 0001..0011 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding 15 test students =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('student01@keel.test', 'Alice'),
    ('student02@keel.test', 'Bob'),
    ('student03@keel.test', 'Carol'),
    ('student04@keel.test', 'Dave'),
    ('student05@keel.test', 'Eve'),
    ('student06@keel.test', 'Frank'),
    ('student07@keel.test', 'Grace'),
    ('student08@keel.test', 'Heidi'),
    ('student09@keel.test', 'Ivan'),
    ('student10@keel.test', 'Judy'),
    ('student11@keel.test', 'Mallory'),
    ('student12@keel.test', 'Niaj'),
    ('student13@keel.test', 'Olivia'),
    ('student14@keel.test', 'Peggy'),
    ('student15@keel.test', 'Rupert');

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 50000, 0 FROM students;
" >/dev/null

echo "== starting fake Discord upstream on 127.0.0.1:$FAKE_DISCORD_PORT =="
KEEL_FAKE_DISCORD_PORT="$FAKE_DISCORD_PORT" \
    python3 "$FAKE_DISCORD" >> "$SERVER_LOG" 2>&1 &
FAKE_DISCORD_PID=$!
wait_ready "$FAKE_DISCORD_PID" "$FAKE_DISCORD_PORT" "fake discord upstream"

echo "== starting practice service on 127.0.0.1:$PRACTICE_PORT =="
echo "2026-08-29T16:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_DISCORD_API_URL="http://127.0.0.1:$FAKE_DISCORD_PORT"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice service"

echo "== running pod tooling and weekly post smoke checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-pods-checks.py"

echo "== ALL SMOKE POD CHECKS PASSED =="
