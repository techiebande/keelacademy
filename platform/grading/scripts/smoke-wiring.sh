#!/usr/bin/env bash
# smoke-wiring.sh — S1.8 end-to-end proof harness: intake-shaped seed ->
# worker -> REAL verdict produced by (a) Layer-1 sandbox checks and (b) the
# Layer-2 judge calling the model through the budget-enforcing proxy.
#
# Scratch postgres:16-alpine (0001+0002+0003), fake OpenAI upstream (canned
# judge verdict), proxy pointed at it, submissions rooted in a scratch dir
# seeded from content/golden/3.2.1/s01-textbook + the variant corpus, sandbox
# image keel-runner:0.1 (pytest + pydantic for the checks). Checks (a)-(d)
# via smoke-wiring-checks.py; a gated LIVE variant (KEEL_WIRING_LIVE=1, one
# real judge call) runs last when requested. Exits non-zero on any failure;
# servers, workers, scratch dirs, temp rubrics and the container are always
# removed (deletions verified by the checks script where they matter).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
PROXY="$SCRIPT_DIR/../proxy/server.py"
FAKE="$SCRIPT_DIR/../proxy/fake_upstream.py"
WORKER="$SCRIPT_DIR/../worker.py"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
IMAGE="postgres:16-alpine"
CONTAINER="keel-wiring-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""
FAKE_PORT=""
PROXY_PORT=""
FAKE_PID=""
PROXY_PID=""
SERVER_LOG="$(mktemp /tmp/keel-wiring-servers.XXXXXX.log)"
TRACE_LOG="$(mktemp /tmp/keel-wiring-trace.XXXXXX.jsonl)"
SUBS_DIR="$(mktemp -d /tmp/keel-wiring-subs.XXXXXX)"
RUBRIC_V2=""

# Canned judge verdict the fake upstream returns: a clean pass carrying the
# five rubric-3.2.1 criterion ids (the judge recomputes overall and would
# reject any disagreement, so this exercises the full validation path).
FAKE_VERDICT='{"criteria":[{"id":"schema-constrained-generation","verdict":"pass","evidence":"fake-upstream evidence"},{"id":"pydantic-validation-boundary","verdict":"pass","evidence":"fake-upstream evidence"},{"id":"defined-fallback","verdict":"pass","evidence":"fake-upstream evidence"},{"id":"failures-logged","verdict":"pass","evidence":"fake-upstream evidence"},{"id":"conservation-tested","verdict":"pass","evidence":"fake-upstream evidence"}],"overall":"pass"}'

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
    # A worker SIGKILLed mid-layer1 can orphan runner.py children; sweep any
    # containers they leave behind (they remove their own on clean paths).
    "$DOCKER" ps -a --format '{{.Names}}' \
        | grep -E '^keel-(sbx|grader)-' \
        | xargs -r "$DOCKER" rm -f -v >/dev/null 2>&1 || true
    if [ -n "$RUBRIC_V2" ] && [ -e "$RUBRIC_V2" ]; then
        rm -f "$RUBRIC_V2"
    fi
    if [ -n "$DB_PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
    rm -rf "$SUBS_DIR" "$SERVER_LOG" "$TRACE_LOG" \
           /tmp/keel-layer1-* /tmp/keel-verdict-* 2>/dev/null || true
    find "$REPO_ROOT" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

DB_PORT="$(free_port)"
FAKE_PORT="$(free_port)"
PROXY_PORT="$(free_port)"

echo "== starting $IMAGE on 127.0.0.1:$DB_PORT =="
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    "$IMAGE" >/dev/null

# Readiness: a real `select 1` (pg_isready lies during postgres's init restart).
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

echo "== seeding alice (cap 5000) + dave (cap 100, already exhausted) =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('dave@keel.test', 'Dave');
INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, cap, used FROM (VALUES
    ('alice@keel.test', 5000, 0),
    ('dave@keel.test', 100, 100)
) AS s(email, cap, used) JOIN students ON students.email = s.email;" >/dev/null

echo "== starting fake upstream on 127.0.0.1:$FAKE_PORT (canned judge verdict, 5s hold) =="
# The 5s hold keeps each judge call in flight long enough for check (b) to
# SIGKILL the worker demonstrably mid-judge.
KEEL_FAKE_PORT="$FAKE_PORT" \
KEEL_FAKE_CONTENT="$FAKE_VERDICT" \
KEEL_FAKE_DELAY_S="5" \
    python3 "$FAKE" >>"$SERVER_LOG" 2>&1 &
FAKE_PID=$!

echo "== starting proxy on 127.0.0.1:$PROXY_PORT (upstream -> fake) =="
KEEL_PROXY_PORT="$PROXY_PORT" \
KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$FAKE_PORT/v1" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
    python3 "$PROXY" >>"$SERVER_LOG" 2>&1 &
PROXY_PID=$!

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
wait_ready "$FAKE_PID" "$FAKE_PORT" "fake upstream"
wait_ready "$PROXY_PID" "$PROXY_PORT" "proxy"

echo "== running wiring checks (a)-(d) =="
export WIRING_DOCKER="$DOCKER" \
       WIRING_CONTAINER="$CONTAINER" \
       WIRING_DB_USER="$DB_USER" \
       WIRING_DB_NAME="$DB_NAME" \
       WIRING_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
       WIRING_WORKER="$WORKER" \
       WIRING_SUBS_DIR="$SUBS_DIR" \
       WIRING_TRACE_LOG="$TRACE_LOG" \
       WIRING_PROXY_PORT="$PROXY_PORT" \
       WIRING_FAKE_PORT="$FAKE_PORT" \
       WIRING_SERVER_LOG="$SERVER_LOG" \
       WIRING_REPO_ROOT="$REPO_ROOT" \
       KEEL_PROXY_URL="http://127.0.0.1:$PROXY_PORT" \
       KEEL_SUBMISSIONS_DIR="$SUBS_DIR" \
       KEEL_TRACE_LOG="$TRACE_LOG" \
       KEEL_SANDBOX_IMAGE="keel-runner:0.1" \
       KEEL_GRADE_SLEEP_S="0.2" \
       KEEL_STALE_AFTER_S="0"
python3 "$SCRIPT_DIR/smoke-wiring-checks.py"

# ---- LIVE: gated, one real judge call through the proxy ----
if [ "${KEEL_WIRING_LIVE:-0}" = "1" ]; then
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo "FAIL (live): KEEL_WIRING_LIVE=1 but OPENAI_API_KEY not in env" >&2
        exit 1
    fi
    echo "== LIVE: one real judge call through a real-upstream proxy =="
    LIVE_PORT="$(free_port)"
    KEEL_PROXY_PORT="$LIVE_PORT" \
    KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
        python3 "$PROXY" >>"$SERVER_LOG" 2>&1 &
    LIVE_PID=$!
    wait_ready "$LIVE_PID" "$LIVE_PORT" "live proxy"
    if ! WIRING_LIVE_PROXY_PORT="$LIVE_PORT" \
         WIRING_DOCKER="$DOCKER" WIRING_CONTAINER="$CONTAINER" \
         WIRING_DB_USER="$DB_USER" WIRING_DB_NAME="$DB_NAME" \
         WIRING_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
         WIRING_WORKER="$WORKER" WIRING_SUBS_DIR="$SUBS_DIR" \
         WIRING_TRACE_LOG="$TRACE_LOG" \
         KEEL_PROXY_URL="http://127.0.0.1:$LIVE_PORT" \
         KEEL_SUBMISSIONS_DIR="$SUBS_DIR" \
         KEEL_TRACE_LOG="$TRACE_LOG" \
         KEEL_SANDBOX_IMAGE="keel-runner:0.1" \
         KEEL_STALE_AFTER_S="0" \
         python3 "$SCRIPT_DIR/smoke-wiring-live-checks.py"; then
        kill "$LIVE_PID" >/dev/null 2>&1 || true
        exit 1
    fi
    kill "$LIVE_PID" >/dev/null 2>&1 || true
else
    echo "(LIVE check skipped: KEEL_WIRING_LIVE != 1)"
fi

echo "== ALL CHECKS PASSED =="
