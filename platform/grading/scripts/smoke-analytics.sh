#!/usr/bin/env bash
# smoke-analytics.sh — S4.7 deterministic proof: Per-unit drop-off & analytics aggregation engine,
# macro funnel conversions, friction metrics (drop-off %, retrieval fail %, retry attempts, concierge volume),
# operations KPIs, phase filtering, and auth boundaries.
#
# Scratch postgres:16-alpine (0001..0014) seeded with synthetic student cohorts:
# - Cohort A (Alice, Bob, Carol): Smooth progress & capstone defense clearance
# - Cohort B (Dave): Stuck on Unit 3.2.1 (multiple failed retrieval checks + heavy concierge questions)
# - Cohort C (Eve): Dropped out after initial enrollment without completing diagnostic
#
# Runs:
# - practice/server.py (with analytics endpoints)
# - smoke-analytics-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-analytics-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-analytics-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-analytics-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-analytics-now.XXXXXX.txt)"

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
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-analytics-* 2>/dev/null || true
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

echo "== applying schema 0001..0014 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery 0014_simulations; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding synthetic test cohorts, events, attempts, verdicts, and turns =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
-- 1. Students (5 students: Alice, Bob, Carol, Dave, Eve)
INSERT INTO students (id, email, display_name, created_at) VALUES
    (1, 'alice@keel.test', 'Alice Engineer', clock_timestamp() - interval '40 days'),
    (2, 'bob@keel.test', 'Bob Builder', clock_timestamp() - interval '35 days'),
    (3, 'carol@keel.test', 'Carol Creator', clock_timestamp() - interval '30 days'),
    (4, 'dave@keel.test', 'Dave Struggling', clock_timestamp() - interval '15 days'),
    (5, 'eve@keel.test', 'Eve Dropped', clock_timestamp() - interval '10 days');

SELECT setval('students_id_seq', 10);

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 100000, 5000 FROM students;

-- 2. Enrollments
INSERT INTO enrollments (student_id, unit_id, status, enrolled_at) VALUES
    (1, '1.1', 'active', clock_timestamp() - interval '39 days'),
    (1, '3.2.1', 'active', clock_timestamp() - interval '25 days'),
    (2, '1.1', 'active', clock_timestamp() - interval '34 days'),
    (2, '5.1', 'active', clock_timestamp() - interval '20 days'),
    (3, '12.1', 'active', clock_timestamp() - interval '29 days'),
    (4, '3.2.1', 'active', clock_timestamp() - interval '14 days');

-- 3. Diagnostic Attempts (Alice, Bob, Carol, Dave completed diagnostic; Eve dropped out before)
INSERT INTO diagnostic_attempts (student_id, diagnostic_id, passed, score_pct, points_earned, points_possible, route, answers_json, breakdown_json, created_at) VALUES
    (1, 'placement-phase-1', true, 90.0, 9, 10, '1.3_skip', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '39 days'),
    (2, 'placement-phase-1', true, 80.0, 8, 10, '1.3_skip', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '34 days'),
    (3, 'placement-phase-1', true, 100.0, 10, 10, '1.3_skip', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '29 days'),
    (4, 'placement-phase-1', false, 40.0, 4, 10, 'baseline_0.1', '{}'::jsonb, '[]'::jsonb, clock_timestamp() - interval '14 days');

-- 4. Submissions & Verdicts
-- Alice: Unit 1.1 -> PASS (1 attempt)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (1, 1, '1.1', 'sha-alice-1', 'https://github.com/alice/1.1', 'graded', clock_timestamp() - interval '38 days');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (1, 'rubric-1.1', 1, 'pass', '{\"overall\": \"pass\"}'::jsonb, clock_timestamp() - interval '38 days');

-- Bob: Unit 1.1 -> PASS (1 attempt)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (2, 2, '1.1', 'sha-bob-1', 'https://github.com/bob/1.1', 'graded', clock_timestamp() - interval '33 days');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (2, 'rubric-1.1', 1, 'pass', '{\"overall\": \"pass\"}'::jsonb, clock_timestamp() - interval '33 days');

-- Bob: Unit 5.1 -> PASS (Phase Integration Gate)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (3, 2, '5.1', 'sha-bob-51', 'https://github.com/bob/5.1', 'graded', clock_timestamp() - interval '18 days');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (3, 'rubric-5.1', 1, 'pass', '{\"overall\": \"pass\"}'::jsonb, clock_timestamp() - interval '18 days');

-- Carol: Unit 12.1 -> PASS (Capstone)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (4, 3, '12.1', 'sha-carol-121', 'https://github.com/carol/12.1', 'graded', clock_timestamp() - interval '10 days');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (4, 'rubric-12.1', 1, 'pass', '{\"overall\": \"pass\"}'::jsonb, clock_timestamp() - interval '10 days');

-- Dave: Unit 3.2.1 -> 3 FAIL submissions (Stuck Cohort)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES 
    (5, 4, '3.2.1', 'sha-dave-1', 'https://github.com/dave/3.2.1', 'graded', clock_timestamp() - interval '12 days'),
    (6, 4, '3.2.1', 'sha-dave-2', 'https://github.com/dave/3.2.1', 'graded', clock_timestamp() - interval '11 days'),
    (7, 4, '3.2.1', 'sha-dave-3', 'https://github.com/dave/3.2.1', 'graded', clock_timestamp() - interval '10 days');

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at) VALUES
    (5, 'rubric-3.2.1', 1, 'fail', '{\"overall\": \"fail\", \"judge\": {\"criteria\": [{\"id\": \"c1-few-shot-format\", \"verdict\": \"fail\", \"evidence\": \"Few shot format lacks delimiter separator\"}]}}'::jsonb, clock_timestamp() - interval '12 days'),
    (6, 'rubric-3.2.1', 1, 'fail', '{\"overall\": \"fail\", \"judge\": {\"criteria\": [{\"id\": \"c1-few-shot-format\", \"verdict\": \"fail\", \"evidence\": \"Still missing XML tags\"}]}}'::jsonb, clock_timestamp() - interval '11 days'),
    (7, 'rubric-3.2.1', 1, 'fail', '{\"overall\": \"fail\", \"judge\": {\"criteria\": [{\"id\": \"c2-xml-validation\", \"verdict\": \"fail\", \"evidence\": \"Malformed closing tags\"}]}}'::jsonb, clock_timestamp() - interval '10 days');

SELECT setval('submissions_id_seq', 20);
SELECT setval('verdicts_id_seq', 20);

-- 5. Retrieval Attempts (Drills) on Unit 3.2.1
-- Alice: passes seed 0 and 1 on first try
INSERT INTO retrieval_attempts (student_id, unit_id, seed_index, seed_prompt, student_answer, passed, feedback, evidence, verdict_json, created_at) VALUES
    (1, '3.2.1', 0, 'Explain system prompt structure', 'System prompt defines role and XML boundaries', true, 'Clear answer', 'role and XML', '{}'::jsonb, clock_timestamp() - interval '24 days'),
    (1, '3.2.1', 1, 'What is in-context calibration?', 'Providing positive and negative exemplars', true, 'Accurate', 'exemplars', '{}'::jsonb, clock_timestamp() - interval '24 days');

-- Dave: fails seed 0 and 1 on first try
INSERT INTO retrieval_attempts (student_id, unit_id, seed_index, seed_prompt, student_answer, passed, feedback, evidence, verdict_json, created_at) VALUES
    (4, '3.2.1', 0, 'Explain system prompt structure', 'It is just a prompt', false, 'Missing role hierarchy and safety framing', 'None provided', '{}'::jsonb, clock_timestamp() - interval '13 days'),
    (4, '3.2.1', 1, 'What is in-context calibration?', 'I do not know', false, 'Incomplete explanation of few-shot tuning', 'Missing', '{}'::jsonb, clock_timestamp() - interval '13 days');

-- 6. Concierge Turns (Dave asked 4 questions on Unit 3.2.1)
INSERT INTO concierge_turns (student_id, unit_id, mode, question, answer, tokens_charged, created_at) VALUES
    (4, '3.2.1', 'teach', 'How do I structure XML delimiters for few-shot examples?', 'Wrap each exemplar in <example> tags with <input> and <output>.', 300, clock_timestamp() - interval '12 days'),
    (4, '3.2.1', 'teach', 'Why is my judge rubric failing on c1-few-shot-format?', 'Check that your prompt contains at least 3 diverse ground truth exemplars.', 420, clock_timestamp() - interval '11 days'),
    (4, '3.2.1', 'guard', 'Can you give me the complete working solution?', 'I cannot write the solution for you, but let us look at the test failure.', 150, clock_timestamp() - interval '11 days'),
    (4, '3.2.1', 'teach', 'What is the syntax for strict JSON schema output?', 'Use response_format with json_schema type definition.', 350, clock_timestamp() - interval '10 days');

-- 7. Events Spine & Gates
INSERT INTO events (type, payload, occurred_at) VALUES
    ('diagnostic.completed', '{\"student_id\": 1, \"diagnostic_id\": \"placement-phase-1\", \"passed\": true}'::jsonb, clock_timestamp() - interval '39 days'),
    ('diagnostic.completed', '{\"student_id\": 2, \"diagnostic_id\": \"placement-phase-1\", \"passed\": true}'::jsonb, clock_timestamp() - interval '34 days'),
    ('diagnostic.completed', '{\"student_id\": 3, \"diagnostic_id\": \"placement-phase-1\", \"passed\": true}'::jsonb, clock_timestamp() - interval '29 days'),
    ('diagnostic.completed', '{\"student_id\": 4, \"diagnostic_id\": \"placement-phase-1\", \"passed\": false}'::jsonb, clock_timestamp() - interval '14 days'),
    ('gate.passed', '{\"student_id\": 2, \"unit_id\": \"5.1\", \"gate_id\": \"phase-5\"}'::jsonb, clock_timestamp() - interval '18 days'),
    ('gate.passed', '{\"student_id\": 3, \"unit_id\": \"12.1\", \"gate_id\": \"capstone\"}'::jsonb, clock_timestamp() - interval '10 days'),
    ('gate.defense_cleared', '{\"student_id\": 3, \"technical_stakeholder_passed\": true, \"business_owner_passed\": true}'::jsonb, clock_timestamp() - interval '9 days');

-- 8. Pods & Memberships (Alice, Bob, Carol active members with posts)
INSERT INTO pods (id, name, cohort_week) VALUES (1, 'Pod 2026-W34-1', '2026-W34');
INSERT INTO pod_memberships (pod_id, student_id, active) VALUES
    (1, 1, true),
    (1, 2, true),
    (1, 3, true);

INSERT INTO pod_posts (pod_id, student_id, week_number, shipped_text, broke_text, next_text, created_at) VALUES
    (1, 1, 1, 'Shipped Pydantic parsing', 'Docker volume mounting', 'Prompt engineering', clock_timestamp() - interval '20 days'),
    (1, 2, 1, 'Shipped agent triage', 'Async queue deadlocks', 'Fine tuning', clock_timestamp() - interval '15 days'),
    (1, 3, 1, 'Shipped capstone deployment', 'Latency spikes', 'Client proposals', clock_timestamp() - interval '8 days');
" >/dev/null

echo "== starting practice service on 127.0.0.1:$PRACTICE_PORT =="
echo "2026-08-29T16:00:00+00:00" > "$NOW_FILE"
export KEEL_DB_CMD="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
export KEEL_ENROLL_SECRET="$APP_TOKEN"
export KEEL_PRACTICE_PORT="$PRACTICE_PORT"
export KEEL_PRACTICE_NOW_FILE="$NOW_FILE"
export KEEL_PRACTICE_NOW="2026-08-29T16:00:00+00:00"

python3 "$PRACTICE_SERVER" >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_ready "$SERVER_PID" "$PRACTICE_PORT" "practice service"

echo "== running per-unit drop-off & analytics smoke checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-analytics-checks.py"

echo "== ALL SMOKE ANALYTICS CHECKS PASSED =="
