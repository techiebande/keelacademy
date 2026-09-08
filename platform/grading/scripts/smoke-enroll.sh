#!/usr/bin/env bash
# smoke-enroll.sh — S2.5 deterministic proof: auth bridge + Stripe Checkout
# enrollment, fully offline.
#
# Scratch postgres:16-alpine (0001..0004), the offline fake Stripe
# (enroll/fake_stripe.py), and the enroll service pointed at it. Checks run
# in smoke-enroll-checks.py: identity bridge (new/claim/conflict), checkout
# session creation through the fake, the full pay -> signed webhook ->
# enrollment loop, webhook replay idempotency (exactly one enrollment, one
# event), tampered + stale signatures rejected with zero writes, unknown
# sessions logged not enrolled, and the student-scoped read endpoints.
# Exits non-zero on any failure; the container and both servers are always
# removed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE="$SCRIPT_DIR/../enroll/fake_stripe.py"
IMAGE="postgres:16-alpine"
CONTAINER="keel-enroll-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""
FAKE_PORT=""
ENROLL_PORT=""
FAKE_PID=""
ENROLL_PID=""
SERVER_LOG="$(mktemp /tmp/keel-enroll-servers.XXXXXX.log)"

# Test-mode placeholders only: no real Stripe key ever appears here or in
# any log the harness writes. The fake does not validate the bearer.
export KEEL_ENROLL_SECRET="test-app-token-smoke"
export KEEL_STRIPE_WEBHOOK_SECRET="whsec_test_placeholder"
export STRIPE_SECRET_KEY="sk_test_placeholder_not_a_real_key"
export KEEL_PRICE_CENTS_3_2_1="1234"
export KEEL_DEFAULT_BUDGET_TOKENS="5000"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

cleanup() {
    for pid in "$FAKE_PID" "$ENROLL_PID"; do
        if [ -n "$pid" ]; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
    if [ -n "$DB_PORT" ]; then
        "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    fi
    rm -f "$SERVER_LOG" 2>/dev/null || true
    find "$SCRIPT_DIR/.." -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

DB_PORT="$(free_port)"
FAKE_PORT="$(free_port)"
ENROLL_PORT="$(free_port)"
DB_CMD=("$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME")

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

echo "== applying schema 0001 + 0002 + 0003 + 0004 + 0005 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding alice (with one graded submission) + dave =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES
    ('alice@keel.test', 'Alice'),
    ('dave@keel.test', 'Dave');
INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, status)
SELECT id, '3.2.1', 'aa11bb22cc33', 'https://example/keel-3.2.1-alice', 'graded'
FROM students WHERE email = 'alice@keel.test';
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
SELECT id, 'rubric-3.2.1', 1, 'pass', '{\"overall\": \"pass\"}'
FROM submissions WHERE commit_sha = 'aa11bb22cc33';" >/dev/null

echo "== starting fake stripe on 127.0.0.1:$FAKE_PORT =="
KEEL_FAKE_STRIPE_PORT="$FAKE_PORT" \
KEEL_FAKE_STRIPE_WEBHOOK_URL="http://127.0.0.1:$ENROLL_PORT/webhook/stripe" \
KEEL_FAKE_STRIPE_WEBHOOK_SECRET="$KEEL_STRIPE_WEBHOOK_SECRET" \
    python3 "$FAKE" >>"$SERVER_LOG" 2>&1 &
FAKE_PID=$!

echo "== starting enroll service on 127.0.0.1:$ENROLL_PORT (stripe -> fake) =="
KEEL_ENROLL_PORT="$ENROLL_PORT" \
KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
KEEL_STRIPE_API_URL="http://127.0.0.1:$FAKE_PORT/v1" \
    python3 "$ENROLL" >>"$SERVER_LOG" 2>&1 &
ENROLL_PID=$!

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
wait_ready "$FAKE_PID" "$FAKE_PORT" "fake stripe"
wait_ready "$ENROLL_PID" "$ENROLL_PORT" "enroll service"

echo "== running enroll checks =="
ENROLL_SMOKE_PORT="$ENROLL_PORT" \
ENROLL_SMOKE_FAKE_PORT="$FAKE_PORT" \
ENROLL_SMOKE_TOKEN="$KEEL_ENROLL_SECRET" \
ENROLL_SMOKE_WEBHOOK_SECRET="$KEEL_STRIPE_WEBHOOK_SECRET" \
ENROLL_SMOKE_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME" \
ENROLL_SMOKE_SERVER_PY="$ENROLL" \
    python3 "$SCRIPT_DIR/smoke-enroll-checks.py"

echo "== ALL CHECKS PASSED =="
