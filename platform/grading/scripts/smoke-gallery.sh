#!/usr/bin/env bash
# smoke-gallery.sh — S4.4 deterministic proof: Public build gallery v1,
# publication eligibility gating (only passing submissions allowed),
# opt-in/unpublish lifecycle, phase/unit filtering, public discoverability,
# atomic spine events ('gallery.published', 'gallery.unpublished'),
# and strict auth/ownership boundaries.
#
# Scratch postgres:16-alpine (0001..0013) seeded with verified passing and failing submissions.
#
# Runs:
# - practice/server.py (with gallery endpoints)
# - smoke-gallery-checks.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
IMAGE="postgres:16-alpine"
CONTAINER="keel-gallery-smoke-$$"
DB_USER="smoke"
DB_NAME="grading"
PRACTICE_SERVER="$SCRIPT_DIR/../practice/server.py"

APP_TOKEN="smoke-gallery-token-$$"
SERVER_LOG="$(mktemp /tmp/keel-gallery-servers.XXXXXX.log)"
NOW_FILE="$(mktemp /tmp/keel-gallery-now.XXXXXX.txt)"

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
    rm -f "$SERVER_LOG" "$NOW_FILE" /tmp/keel-gallery-* 2>/dev/null || true
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

echo "== applying schema 0001..0013 =="
for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge 0010_diagnostic 0011_pods 0012_digests 0013_gallery; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding test students, submissions, and verdicts =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
-- 1. Students
INSERT INTO students (id, email, display_name) VALUES
    (1, 'alice@keel.test', 'Alice Engineer'),
    (2, 'bob@keel.test', 'Bob Builder'),
    (3, 'carol@keel.test', 'Carol Creator');

SELECT setval('students_id_seq', 10);

INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 50000, 1000 FROM students;

-- 2. Submissions & Verdicts
-- Alice: Submission 1 (Unit 1.1 -> PASS)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (1, 1, '1.1', 'a1b2c3d4e5f6', 'https://github.com/alice/unit1.1', 'graded', clock_timestamp() - interval '5 days');

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (1, 'rubric-1.1', 1, 'pass', jsonb_build_object(
    'judge', jsonb_build_object(
        'overall', 'pass',
        'criteria', jsonb_build_array(
            jsonb_build_object('id', 'c1-pydantic-validation', 'verdict', 'pass', 'evidence', 'Invoice model strictly validates line_items and amounts.'),
            jsonb_build_object('id', 'c2-type-hints', 'verdict', 'pass', 'evidence', 'Complete type coverage across pipeline functions.')
        )
    ),
    'layer1', jsonb_build_object(
        'overall', 'pass',
        'checks', jsonb_build_array(
            jsonb_build_object('id', 'pytest-unit', 'type', 'pytest', 'status', 'pass', 'note', '5 passed in 0.4s')
        )
    )
), clock_timestamp() - interval '5 days');

-- Alice: Submission 2 (Unit 1.2 -> FAIL)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (2, 1, '1.2', 'b2c3d4e5f6a1', 'https://github.com/alice/unit1.2', 'graded', clock_timestamp() - interval '4 days');

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (2, 'rubric-1.2', 1, 'fail', jsonb_build_object(
    'judge', jsonb_build_object(
        'overall', 'fail',
        'criteria', jsonb_build_array(
            jsonb_build_object('id', 'c1-git-hooks', 'verdict', 'fail', 'evidence', 'Pre-commit hook allows unformatted code to pass.')
        )
    )
), clock_timestamp() - interval '4 days');

-- Alice: Submission 5 (Unit 3.2.1 -> QUEUED, no verdict yet)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (5, 1, '3.2.1', 'e5f6a1b2c3d4', 'https://github.com/alice/unit3.2.1', 'queued', clock_timestamp() - interval '1 hour');

-- Bob: Submission 3 (Unit 5.1 -> PASS)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (3, 2, '5.1', 'c3d4e5f6a1b2', 'https://github.com/bob/agent-triage', 'graded', clock_timestamp() - interval '3 days');

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (3, 'rubric-5.1', 1, 'pass', jsonb_build_object(
    'judge', jsonb_build_object(
        'overall', 'pass',
        'criteria', jsonb_build_array(
            jsonb_build_object('id', 'c1-agent-routing', 'verdict', 'pass', 'evidence', 'Multi-tool agent triages complex merchant dispute variations accurately.')
        )
    )
), clock_timestamp() - interval '3 days');

-- Carol: Submission 4 (Unit 12.1 -> PASS)
INSERT INTO submissions (id, student_id, unit_id, commit_sha, repo_url, status, created_at)
VALUES (4, 3, '12.1', 'd4e5f6a1b2c3', 'https://github.com/carol/capstone-omnicart', 'graded', clock_timestamp() - interval '1 day');

INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at)
VALUES (4, 'rubric-12.1', 1, 'pass', jsonb_build_object(
    'judge', jsonb_build_object(
        'overall', 'pass',
        'criteria', jsonb_build_array(
            jsonb_build_object('id', 'c1-capstone-deployment', 'verdict', 'pass', 'evidence', 'End-to-end dispute resolution pipeline verified in production Docker runner.')
        )
    )
), clock_timestamp() - interval '1 day');

SELECT setval('submissions_id_seq', 20);
SELECT setval('verdicts_id_seq', 20);
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

echo "== running public build gallery smoke checks =="
export KEEL_PRACTICE_URL="http://127.0.0.1:$PRACTICE_PORT"
python3 "$SCRIPT_DIR/smoke-gallery-checks.py"

echo "== ALL SMOKE GALLERY CHECKS PASSED =="
