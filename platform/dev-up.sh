#!/usr/bin/env bash
# platform/dev-up.sh — Spin up the complete Keel Academy development stack:
# Postgres (0001..0014), Fake Stripe, Fake LLM upstream, Proxy, Enroll, Reader,
# Practice/Simulations/Pods, seed data, and Learner App with live wiring.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
SCHEMA_DIR="$REPO_ROOT/platform/grading/schema"

LOG_DIR="/tmp/keel-dev-logs"
STATE_FILE="$LOG_DIR/pids.env"
CONTAINER="keel-dev-pg"
DB_USER="smoke"
DB_NAME="grading"

APP_TOKEN="keel-dev-secret-token"
WHSEC="whsec_dev_stripe_placeholder"
STRIPE_KEY="sk_test_dev_placeholder"
AUTH_SECRET="keel-dev-offline-auth-secret"
PRICE_CENTS="4900"

DB_PORT="5432"
READER_PORT="8790"
ENROLL_PORT="8791"
PRACTICE_PORT="8792"
FAKE_STRIPE_PORT="8793"
FAKE_PADDLE_PORT="8798"
PROXY_PORT="8794"
FAKE_JUDGE_PORT="8795"
APP_PORT="3000"

mkdir -p "$LOG_DIR"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

DB_CMD_PLAIN="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"

wait_port() {
    local port="$1" name="$2" timeout="${3:-30}"
    for i in $(seq 1 "$((timeout * 2))"); do
        if python3 -c "import socket, sys; s=socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=1); s.close()" "$port" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
    done
    echo "FAIL: $name never became ready on port $port" >&2
    return 1
}

# 1. Check & Stop previous processes from state file if any
if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    for pid in "${FAKE_STRIPE_PID:-}" "${FAKE_PADDLE_PID:-}" "${FAKE_JUDGE_PID:-}" "${PROXY_PID:-}" "${ENROLL_PID:-}" "${READER_PID:-}" "${PRACTICE_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
fi

# Also kill any stale python servers on these ports
for p in $READER_PORT $ENROLL_PORT $PRACTICE_PORT $FAKE_STRIPE_PORT $PROXY_PORT $FAKE_JUDGE_PORT 8798; do
    fuser -k -n tcp "$p" 2>/dev/null || true
done

# 2. Start PostgreSQL container
echo "== [1/6] Starting Postgres container ($CONTAINER) on port $DB_PORT =="
"$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD=smoke \
    -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" \
    postgres:16-alpine >/dev/null

for i in $(seq 1 30); do
    if "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select 1;" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# 3. Apply migrations 0001..0016
echo "== [2/6] Applying Postgres migrations 0001..0016 =="
for mig in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery 0014_simulations 0015_auth 0016_subscriptions; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$mig.sql" >/dev/null
done

# 4. Seed database with full test student data
echo "== [3/6] Seeding test students, enrollments, budgets, pods, simulations & verdicts =="
"$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 << 'EOSQL'
-- Students
INSERT INTO students (id, email, display_name, external_auth_id, created_at) VALUES
    (1, 'alice@keel.test', 'Alice Engineer', 'offline_180b54fd34941ac9', clock_timestamp() - interval '40 days'),
    (2, 'bob@keel.test', 'Bob Builder', 'offline_bob', clock_timestamp() - interval '35 days'),
    (3, 'carol@keel.test', 'Carol Creator', 'offline_carol', clock_timestamp() - interval '30 days'),
    (4, 'dave@keel.test', 'Dave Struggling', 'offline_dave', clock_timestamp() - interval '15 days'),
    (5, 'eve@keel.test', 'Eve Dropped', 'offline_eve', clock_timestamp() - interval '10 days')
ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, external_auth_id = EXCLUDED.external_auth_id;

SELECT setval('students_id_seq', 10);

-- Budgets (500,000 tokens for Alice)
INSERT INTO budgets (student_id, tokens_cap, tokens_used) VALUES
    (1, 500000, 4200),
    (2, 100000, 1500),
    (3, 100000, 3200),
    (4, 100000, 8900),
    (5, 100000, 0)
ON CONFLICT (student_id) DO UPDATE SET tokens_cap = EXCLUDED.tokens_cap;

-- Enrollments: Alice and peers enrolled in planned milestone units
INSERT INTO enrollments (student_id, unit_id, status, enrolled_at) VALUES
    (1, '1.1', 'active', clock_timestamp() - interval '28 days'),
    (2, '1.1', 'active', clock_timestamp() - interval '34 days'),
    (2, '5.1', 'active', clock_timestamp() - interval '20 days'),
    (3, '12.1', 'active', clock_timestamp() - interval '29 days')
ON CONFLICT (student_id, unit_id) DO NOTHING;

-- Diagnostics
INSERT INTO diagnostic_attempts (student_id, diagnostic_id, passed, score_pct, points_earned, points_possible, route, answers_json, breakdown_json, created_at) VALUES
    (1, 'placement-phase-1', true, 100.0, 10, 10, '1.3_skip', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '39 days'),
    (2, 'placement-phase-1', true, 80.0, 8, 10, '1.3_skip', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '34 days'),
    (4, 'placement-phase-1', false, 40.0, 4, 10, 'baseline_0.1', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '14 days')
ON CONFLICT DO NOTHING;

-- Submissions & Verdicts (Alice passing 3.2.1 and 1.1)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at) VALUES
    (1, 1, '1.1', 'sha-alice-1', 'https://github.com/alice/1.1', 'graded', clock_timestamp() - interval '28 days'),
    (2, 1, '3.2.1', 'sha-alice-321', 'https://github.com/alice/3.2.1', 'graded', clock_timestamp() - interval '20 days')
ON CONFLICT (id) DO NOTHING;

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at) VALUES
    (1, 'rubric-1.1', 1, 'pass', '{"overall": "pass"}'::jsonb, clock_timestamp() - interval '28 days'),
    (2, 'rubric-3.2.1', 1, 'pass', '{"overall": "pass", "judge": {"criteria": [{"id": "c1-few-shot-format", "verdict": "pass", "evidence": "Valid tags"}, {"id": "c2-xml-validation", "verdict": "pass", "evidence": "Valid schemas"}]}}'::jsonb, clock_timestamp() - interval '20 days')
ON CONFLICT (submission_id) DO NOTHING;

SELECT setval('submissions_id_seq', 20);
SELECT setval('verdicts_id_seq', 20);

-- Retrieval attempts
INSERT INTO retrieval_attempts (student_id, unit_id, seed_index, seed_prompt, student_answer, passed, feedback, evidence, verdict_json, created_at) VALUES
    (1, '3.2.1', 0, 'Explain system prompt structure', 'System prompt defines role and XML boundaries', true, 'Clear answer', 'role and XML', '{}'::jsonb, clock_timestamp() - interval '24 days'),
    (1, '3.2.1', 1, 'What is in-context calibration?', 'Providing positive and negative exemplars', true, 'Accurate', 'exemplars', '{}'::jsonb, clock_timestamp() - interval '24 days')
ON CONFLICT DO NOTHING;

-- Pods & Pod memberships
INSERT INTO pods (id, name, cohort_week) VALUES (1, 'Pod 2026-W34-Alpha', '2026-W34')
ON CONFLICT (id) DO NOTHING;

INSERT INTO pod_memberships (pod_id, student_id, active) VALUES
    (1, 1, true),
    (1, 2, true),
    (1, 3, true)
ON CONFLICT DO NOTHING;

INSERT INTO pod_posts (pod_id, student_id, week_number, shipped_text, broke_text, next_text, created_at) VALUES
    (1, 1, 1, 'Shipped Pydantic validation & schemas', 'Docker mount edge cases', 'LLM few-shot prompts', clock_timestamp() - interval '5 days')
ON CONFLICT DO NOTHING;

-- Gallery Projects
INSERT INTO gallery_projects (student_id, unit_id, submission_id, title, description, repo_url, demo_url, published) VALUES
    (1, '3.2.1', 2, 'Few-Shot OmniCart Extractor', 'Clean few-shot extractor with strict Pydantic parsing and robust XML delimiters.', 'https://github.com/alice/keel-3.2.1', 'https://demo.omnicart.test/alice', true)
ON CONFLICT (student_id, unit_id) DO NOTHING;

-- Simulations
INSERT INTO simulations (student_id, persona_id, status, turns_json, score_pct, passed, created_at, completed_at) VALUES
    (1, 'discovery-call', 'graded', '[{"role": "assistant", "content": "Hello Sarah, could you walk me through where your team spends the most time in daily ops?"}, {"role": "user", "content": "We spend about 14 hours a week manually re-keying shipping documents."}]'::jsonb, 92.0, true, clock_timestamp() - interval '3 days', clock_timestamp() - interval '3 days')
ON CONFLICT DO NOTHING;
EOSQL

# 5. Seed offline auth JSON store
cat > /tmp/keel-offline-auth.json << 'EOF'
{
  "users": [
    {
      "externalId": "offline_180b54fd34941ac9",
      "email": "alice@keel.test",
      "name": "Alice Engineer"
    },
    {
      "externalId": "offline_admin",
      "email": "admin@keelacademy.com",
      "name": "Staff Admin"
    },
    {
      "externalId": "offline_4bdd1923faf820d0",
      "email": "samuel.ochaba.dev@gmail.com",
      "name": "Samuel Ochaba"
    }
  ]
}
EOF

# 6. Start Backend Python Microservices
echo "== [4/6] Starting background Python microservices =="

# Load local secrets from ~/.keelacademy/app.env if present
if [ -f "$HOME/.keelacademy/app.env" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$HOME/.keelacademy/app.env"
    set +a
fi

BILLING_PROVIDER="${KEEL_BILLING_PROVIDER:-fake}"
FAKE_PADDLE_PID=""

if [ "$BILLING_PROVIDER" = "paddle" ]; then
    echo "Using real Paddle billing (provider: paddle)"
    ( exec env KEEL_ENROLL_PORT="$ENROLL_PORT" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_BILLING_PROVIDER="paddle" \
        PADDLE_API_KEY="${PADDLE_API_KEY:-}" \
        PADDLE_PRICE_ID="${PADDLE_PRICE_ID:-}" \
        KEEL_PADDLE_API_URL="${KEEL_PADDLE_API_URL:-https://sandbox-api.paddle.com}" \
        KEEL_PADDLE_WEBHOOK_SECRET="${KEEL_PADDLE_WEBHOOK_SECRET:-}" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        KEEL_DEFAULT_BUDGET_TOKENS="100000" \
        RESEND_API_KEY="${RESEND_API_KEY:-}" \
        setsid python3 "$REPO_ROOT/platform/grading/enroll/server.py" ) >> "$LOG_DIR/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!
else
    echo "Using offline fake Paddle billing (port $FAKE_PADDLE_PORT)"
    ( exec env KEEL_FAKE_PADDLE_PORT="$FAKE_PADDLE_PORT" \
        KEEL_FAKE_PADDLE_PRICE_ID="pri_fake_allaccess" \
        KEEL_FAKE_PADDLE_AMOUNT_CENTS="4900" \
        KEEL_FAKE_PADDLE_WEBHOOK_URL="http://127.0.0.1:$ENROLL_PORT/webhook/paddle" \
        KEEL_FAKE_PADDLE_WEBHOOK_SECRET="whsec_fake_paddle" \
        setsid python3 "$REPO_ROOT/platform/grading/enroll/fake_paddle.py" ) >> "$LOG_DIR/fake-paddle.log" 2>&1 < /dev/null &
    FAKE_PADDLE_PID=$!

    ( exec env KEEL_ENROLL_PORT="$ENROLL_PORT" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_BILLING_PROVIDER="fake" \
        KEEL_FAKE_PADDLE_URL="http://127.0.0.1:$FAKE_PADDLE_PORT" \
        KEEL_PADDLE_WEBHOOK_SECRET="whsec_fake_paddle" \
        PADDLE_PRICE_ID="pri_fake_allaccess" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        KEEL_DEFAULT_BUDGET_TOKENS="100000" \
        RESEND_API_KEY="${RESEND_API_KEY:-}" \
        setsid python3 "$REPO_ROOT/platform/grading/enroll/server.py" ) >> "$LOG_DIR/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!
fi

# Fake Judge Upstream
( exec env KEEL_FAKE_PORT="$FAKE_JUDGE_PORT" \
    setsid python3 "$REPO_ROOT/platform/grading/practice/fake_judge_upstream.py" ) >> "$LOG_DIR/fake-judge.log" 2>&1 < /dev/null &
FAKE_JUDGE_PID=$!

# LLM Proxy
( exec env KEEL_PROXY_PORT="$PROXY_PORT" \
    KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$FAKE_JUDGE_PORT/v1" \
    KEEL_DB_CMD="$DB_CMD_PLAIN" \
    setsid python3 "$REPO_ROOT/platform/grading/proxy/server.py" ) >> "$LOG_DIR/proxy.log" 2>&1 < /dev/null &
PROXY_PID=$!

# Reader Service
( exec env KEEL_READER_PORT="$READER_PORT" \
    KEEL_DB_CMD="$DB_CMD_PLAIN" \
    setsid python3 "$REPO_ROOT/platform/grading/reader/server.py" ) >> "$LOG_DIR/reader.log" 2>&1 < /dev/null &
READER_PID=$!

# Practice / Simulations / Pods Service
( exec env KEEL_PRACTICE_PORT="$PRACTICE_PORT" \
    KEEL_DB_CMD="$DB_CMD_PLAIN" \
    KEEL_ENROLL_SECRET="$APP_TOKEN" \
    KEEL_PROXY_URL="http://127.0.0.1:$PROXY_PORT" \
    KEEL_TRACE_LOG="$LOG_DIR/traces.jsonl" \
    KEEL_SANDBOX_IMAGE="keel-runner:0.1" \
    setsid python3 "$REPO_ROOT/platform/grading/practice/server.py" ) >> "$LOG_DIR/practice.log" 2>&1 < /dev/null &
PRACTICE_PID=$!

if [ "$BILLING_PROVIDER" = "fake" ]; then
    wait_port "$FAKE_PADDLE_PORT" "Fake Paddle"
fi
wait_port "$FAKE_JUDGE_PORT" "Fake Judge"
wait_port "$PROXY_PORT" "LLM Proxy"
wait_port "$ENROLL_PORT" "Enroll Service"
wait_port "$READER_PORT" "Reader Service"
wait_port "$PRACTICE_PORT" "Practice Service"

# Save state
cat > "$STATE_FILE" << STATE
FAKE_PADDLE_PID=$FAKE_PADDLE_PID
FAKE_JUDGE_PID=$FAKE_JUDGE_PID
PROXY_PID=$PROXY_PID
ENROLL_PID=$ENROLL_PID
READER_PID=$READER_PID
PRACTICE_PID=$PRACTICE_PID
STATE

# 7. Configure Next.js learner app
echo "== [5/6] Configuring platform/app/.env.local =="
cat > "$APP_DIR/.env.local" << EOF
KEEL_READER_URL=http://127.0.0.1:$READER_PORT
KEEL_ENROLL_URL=http://127.0.0.1:$ENROLL_PORT
KEEL_PRACTICE_URL=http://127.0.0.1:$PRACTICE_PORT
KEEL_AUTH_URL=http://127.0.0.1:$ENROLL_PORT
KEEL_ENROLL_SECRET=$APP_TOKEN
KEEL_OFFLINE_AUTH_SECRET=$AUTH_SECRET
KEEL_OFFLINE_AUTH_STORE=/tmp/keel-offline-auth.json
KEEL_ADMIN_EMAILS=alice@keel.test,admin@keelacademy.com
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID:-}
GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET:-}
RESEND_API_KEY=${RESEND_API_KEY:-}
EOF

# 8. Start / Restart Next.js dev server
echo "== [6/6] Ensuring Next.js learner app is running on port $APP_PORT =="
pkill -9 -f "next-server|node_modules/\.bin/next" 2>/dev/null || true
( cd "$APP_DIR" && exec setsid ./node_modules/.bin/next dev -p "$APP_PORT" -H 127.0.0.1 ) \
    >> "$LOG_DIR/app.log" 2>&1 < /dev/null &
APP_PID=$!
echo "APP_PID=$APP_PID" >> "$STATE_FILE"

wait_port "$APP_PORT" "Next.js Learner App" 60

echo ""
echo "================================================================="
echo "  KEEL ACADEMY PLATFORM IS FULLY UP & RUNNING"
echo "================================================================="
echo "  Learner App      : http://localhost:3000"
echo "  Sign In URL      : http://localhost:3000/sign-in"
echo "  Test Student     : alice@keel.test (no password needed)"
echo "  Dashboard        : http://localhost:3000/me"
echo "  Curriculum Map   : http://localhost:3000/map"
echo "  Unit 3.2.1       : http://localhost:3000/units/3.2.1"
echo "  Community / Pods : http://localhost:3000/community"
echo "  Simulations      : http://localhost:3000/simulations"
echo "  Build Gallery    : http://localhost:3000/gallery"
echo "  Staff Telemetry  : http://localhost:3000/admin/analytics"
echo "-----------------------------------------------------------------"
echo "  Reader Svc (:8790) | Enroll Svc (:8791) | Practice Svc (:8792)"
echo "  Billing: $BILLING_PROVIDER     | LLM Proxy (:8794)  | Postgres (:5432)"
echo "  Logs located in: $LOG_DIR"
echo "================================================================="
