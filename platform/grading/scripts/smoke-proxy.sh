#!/usr/bin/env bash
# smoke-proxy.sh — S1.5 proof harness. Spins up a scratch postgres:16-alpine
# (0001+0002+0003 applied), seeds alice (cap 5000) / bob (cap 300) /
# carol (cap 400), starts the fake upstream + proxy on random ports with
# KEEL_PROXY_UPSTREAM_URL pointing at the fake, and runs checks (a)-(e) via
# python3 stdlib. Check (f) is LIVE and only runs when KEEL_PROXY_LIVE=1
# (one real gpt-4o-mini call, cost < $0.01); reported as skipped otherwise.
# Exits non-zero on any failure; servers killed and container always removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
PROXY="$SCRIPT_DIR/../proxy/server.py"
FAKE="$SCRIPT_DIR/../proxy/fake_upstream.py"
IMAGE="postgres:16-alpine"
CONTAINER="keel-proxy-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""
FAKE_PORT=""
PROXY_PORT=""
FAKE_PID=""
PROXY_PID=""
SERVER_LOG="$(mktemp /tmp/keel-proxy-servers.XXXXXX.log)"

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
    for pid in "$FAKE_PID" "$PROXY_PID"; do
        if [ -n "$pid" ]; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
    if [ -n "$DB_PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
    rm -f "$SERVER_LOG"
}
trap cleanup EXIT

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

DB_PORT="$(free_port)"
FAKE_PORT="$(free_port)"
PROXY_PORT="$(free_port)"

wait_ready() {  # $1 = pid, $2 = port, $3 = name
    for i in $(seq 1 60); do
        if ! kill -0 "$1" 2>/dev/null; then
            echo "FAIL: $3 died at startup:" >&2
            cat "$SERVER_LOG" >&2 || true
            exit 1
        fi
        if python3 - "$2" <<'EOF' 2>/dev/null
import socket, sys
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=1)
s.close()
EOF
        then
            return 0
        fi
        if [ "$i" -eq 60 ]; then
            echo "FAIL: $3 never became ready" >&2
            exit 1
        fi
        sleep 1
    done
}

echo "== starting $IMAGE on 127.0.0.1:$DB_PORT =="
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    "$IMAGE" >/dev/null

# Readiness: a real `select 1` (pg_isready lies during init — observed S1.1).
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

echo "== applying schema 0001 + 0002 + 0003 =="
for m in 0001_init 0002_intake 0003_budgets; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding students + budgets (alice 5000, bob 300, carol 400) =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('bob@keel.test', 'Bob'),
    ('carol@keel.test', 'Carol');
INSERT INTO budgets (student_id, tokens_cap)
SELECT id, cap FROM (VALUES
    ('alice@keel.test', 5000),
    ('bob@keel.test', 300),
    ('carol@keel.test', 400)
) AS s(email, cap) JOIN students ON students.email = s.email;" >/dev/null

echo "== starting fake upstream on 127.0.0.1:$FAKE_PORT =="
KEEL_FAKE_PORT="$FAKE_PORT" python3 "$FAKE" >>"$SERVER_LOG" 2>&1 &
FAKE_PID=$!
wait_ready "$FAKE_PID" "$FAKE_PORT" "fake upstream"

echo "== starting proxy on 127.0.0.1:$PROXY_PORT (upstream -> fake) =="
KEEL_PROXY_PORT="$PROXY_PORT" \
KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$FAKE_PORT/v1" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$PROXY" >>"$SERVER_LOG" 2>&1 &
PROXY_PID=$!
wait_ready "$PROXY_PID" "$PROXY_PORT" "proxy"

echo "== running checks (a)-(e) =="
export PROXY_PORT="$PROXY_PORT" FAKE_PORT="$FAKE_PORT" \
       PROXY_DOCKER="$DOCKER" PROXY_CONTAINER="$CONTAINER" \
       PROXY_DB_USER="$DB_USER" PROXY_DB_NAME="$DB_NAME"
python3 "$SCRIPT_DIR/smoke-proxy-checks.py"

# ---- (f) LIVE: gated, one real gpt-4o-mini call for alice ----
if [ "${KEEL_PROXY_LIVE:-0}" = "1" ]; then
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo "FAIL (f): KEEL_PROXY_LIVE=1 but OPENAI_API_KEY not in env" >&2
        exit 1
    fi
    LIVE_PORT="$(free_port)"
    echo "== (f) LIVE: second proxy on 127.0.0.1:$LIVE_PORT (real upstream) =="
    KEEL_PROXY_PORT="$LIVE_PORT" \
    KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
        python3 "$PROXY" >>"$SERVER_LOG" 2>&1 &
    LIVE_PID=$!
    wait_ready "$LIVE_PID" "$LIVE_PORT" "live proxy"
    if ! PROXY_PORT="$LIVE_PORT" LIVE_DOCKER="$DOCKER" LIVE_CONTAINER="$CONTAINER" \
         python3 "$SCRIPT_DIR/smoke-proxy-live-checks.py"; then
        kill "$LIVE_PID" >/dev/null 2>&1 || true
        exit 1
    fi
    kill "$LIVE_PID" >/dev/null 2>&1 || true
else
    echo "(f) LIVE check skipped (KEEL_PROXY_LIVE != 1)"
fi

echo "== ALL CHECKS PASSED =="
