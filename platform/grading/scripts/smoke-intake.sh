#!/usr/bin/env bash
# smoke-intake.sh — S1.2 proof harness. Spins up a scratch postgres:16-alpine
# (0001 + 0002 applied), seeds a student, starts intake/server.py with a test
# secret in env, and runs five checks (a)-(e) via python3 stdlib. Exits
# non-zero on any failure; server killed and container always removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
SERVER="$SCRIPT_DIR/../intake/server.py"
IMAGE="postgres:16-alpine"
CONTAINER="keel-intake-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""
HTTP_PORT=""
SERVER_PID=""
SERVER_LOG="$(mktemp /tmp/keel-intake-server.XXXXXX.log)"

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
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
    fi
    if [ -n "$DB_PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Pick two random free host ports (same pattern as smoke-schema.sh).
DB_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
HTTP_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"

echo "== starting $IMAGE on 127.0.0.1:$DB_PORT =="
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    "$IMAGE" >/dev/null

# Readiness: a real `select 1` (pg_isready lies during postgres's init
# restart — observed live during S1.1).
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

echo "== starting intake server on 127.0.0.1:$HTTP_PORT =="
# The test secret exists only in this process tree's env.
KEEL_WEBHOOK_SECRET="keel-test-secret-$$" \
KEEL_INTAKE_PORT="$HTTP_PORT" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$SERVER" >/dev/null 2>"$SERVER_LOG" &
SERVER_PID=$!

for i in $(seq 1 60); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "FAIL: intake server died at startup:" >&2
        cat "$SERVER_LOG" >&2 || true
        exit 1
    fi
    if python3 - "$HTTP_PORT" <<'EOF' 2>/dev/null
import socket, sys
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=1)
s.close()
EOF
    then
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "FAIL: intake server never became ready" >&2
        exit 1
    fi
    sleep 1
done

echo "== running checks =="
export INTAKE_PORT="$HTTP_PORT" INTAKE_SECRET="keel-test-secret-$$" \
       INTAKE_DOCKER="$DOCKER" INTAKE_CONTAINER="$CONTAINER" \
       INTAKE_DB_USER="$DB_USER" INTAKE_DB_NAME="$DB_NAME"
python3 "$SCRIPT_DIR/smoke-intake-checks.py" "$SERVER_LOG"
rm -f "$SERVER_LOG"

echo "== ALL CHECKS PASSED =="
