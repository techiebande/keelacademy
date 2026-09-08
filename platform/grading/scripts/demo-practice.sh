#!/usr/bin/env bash
# NOTE: the copy greps below assert the CURRENT PLACEHOLDER copy (pre-redesign).
# A UI session that rewrites copy updates these greps to the new strings and
# re-runs this demo green — see the 2026-08-27 copy-unfreeze decision in build-state.md.
# demo-practice.sh — S3.1 + S3.2 end-to-end proof: completion-problem & retrieval drill practice loop.
#
# Modes:
#   setup     Scratch postgres (0001..0008), offline fake Stripe, fake judge upstream,
#             proxy service, enroll service, reader service, practice service, and learner app under setsid.
#   prove     Drives real sign-up, payment, completion problem submission (RED & GREEN),
#             retrieval drill submission (PASS & FAIL), verifies rendered UI, judge feedback,
#             evidence quotes, token budget charging, attempt history, gate/rebate isolation,
#             and tests unenrolled student 403.
#   teardown  Stops daemons, cleans container and files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE_STRIPE="$SCRIPT_DIR/../enroll/fake_stripe.py"
READER="$SCRIPT_DIR/../reader/server.py"
PROXY="$SCRIPT_DIR/../proxy/server.py"
FAKE_JUDGE="$SCRIPT_DIR/../practice/fake_judge_upstream.py"
PRACTICE="$SCRIPT_DIR/../practice/server.py"
ENGINE="$SCRIPT_DIR/../gates/engine.py"
MACHINE="$SCRIPT_DIR/../rebate/machine.py"

ROOT="/tmp/keel-practice-demo"
CONTAINER="keel-practice-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
STATE_FILE="$ROOT/pids.env"

APP_TOKEN="demo-practice-app-token"
WHSEC="whsec_demo_practice_placeholder"
STRIPE_KEY="sk_test_placeholder_not_a_real_key"
AUTH_SECRET="demo-practice-offline-auth-secret"
PRICE_CENTS="1234"
REBATE_PCT="15"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

DB_CMD_PLAIN="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

psql_sql() {
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA <<< "$1"
}

wait_ready() {
    local pid="$1" port="$2" name="$3"
    for i in $(seq 1 60); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "FAIL: $name died at startup:" >&2
            exit 1
        fi
        if python3 - "$port" <<'EOF' 2>/dev/null
import socket, sys
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=1)
s.close()
EOF
        then
            return 0
        fi
        sleep 0.5
    done
    echo "FAIL: $name never became ready on port $port" >&2
    return 1
}

do_setup() {
    mkdir -p "$ROOT/logs"
    if [ -f "$STATE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$STATE_FILE"
        local alive=1
        for pid in "${ENROLL_PID:-}" "${FAKE_STRIPE_PID:-}" "${FAKE_JUDGE_PID:-}" "${PROXY_PID:-}" "${READER_PID:-}" "${PRACTICE_PID:-}" "${APP_PID:-}"; do
            [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || alive=0
        done
        if [ "$alive" = "1" ]; then
            echo "== demo already up (app :${APP_PORT}, practice :${PRACTICE_PORT}, proxy :${PROXY_PORT}) =="
            return 0
        fi
        do_teardown_inner
    fi

    local db_port enroll_port fake_stripe_port fake_judge_port proxy_port reader_port practice_port app_port
    db_port="$(free_port)"
    fake_stripe_port="$(free_port)"
    fake_judge_port="$(free_port)"
    proxy_port="$(free_port)"
    enroll_port="$(free_port)"
    reader_port="$(free_port)"
    practice_port="$(free_port)"
    app_port="$(free_port)"

    echo "== (1/8) starting postgres on 127.0.0.1:$db_port =="
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    "$DOCKER" run -d --name "$CONTAINER" \
        -e POSTGRES_USER="$DB_USER" \
        -e POSTGRES_PASSWORD=smoke \
        -e POSTGRES_DB="$DB_NAME" \
        -p "127.0.0.1:$db_port:5432" \
        postgres:16-alpine >/dev/null

    for i in $(seq 1 60); do
        if "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select 1;" >/dev/null 2>&1; then
            break
        fi
        [ "$i" -eq 60 ] && { echo "FAIL: postgres timeout" >&2; exit 1; }
        sleep 0.5
    done

    for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates 0007_practice 0008_retrieval 0009_concierge; do
        "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
            < "$SCRIPT_DIR/../schema/$m.sql" >/dev/null
    done

    echo "== (2/8) starting fake stripe on 127.0.0.1:$fake_stripe_port =="
    ( exec env KEEL_FAKE_STRIPE_PORT="$fake_stripe_port" \
        KEEL_FAKE_STRIPE_WEBHOOK_URL="http://127.0.0.1:$enroll_port/webhook/stripe" \
        KEEL_FAKE_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        setsid python3 "$FAKE_STRIPE" ) >> "$ROOT/logs/fake-stripe.log" 2>&1 < /dev/null &
    FAKE_STRIPE_PID=$!

    echo "== (3/8) starting fake judge upstream on 127.0.0.1:$fake_judge_port =="
    ( exec env KEEL_FAKE_PORT="$fake_judge_port" \
        setsid python3 "$FAKE_JUDGE" ) >> "$ROOT/logs/fake-judge.log" 2>&1 < /dev/null &
    FAKE_JUDGE_PID=$!

    echo "== (4/8) starting LLM proxy on 127.0.0.1:$proxy_port =="
    ( exec env KEEL_PROXY_PORT="$proxy_port" \
        KEEL_PROXY_UPSTREAM_URL="http://127.0.0.1:$fake_judge_port/v1" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        setsid python3 "$PROXY" ) >> "$ROOT/logs/proxy.log" 2>&1 < /dev/null &
    PROXY_PID=$!

    echo "== (5/8) starting enroll service on 127.0.0.1:$enroll_port =="
    ( exec env KEEL_ENROLL_PORT="$enroll_port" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_STRIPE_API_URL="http://127.0.0.1:$fake_stripe_port/v1" \
        STRIPE_SECRET_KEY="$STRIPE_KEY" \
        KEEL_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        KEEL_PRICE_CENTS_3_2_1="$PRICE_CENTS" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        KEEL_DEFAULT_BUDGET_TOKENS="5000" \
        setsid python3 "$ENROLL" ) >> "$ROOT/logs/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!

    echo "== (6/8) starting reader service on 127.0.0.1:$reader_port =="
    ( exec env KEEL_READER_PORT="$reader_port" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        setsid python3 "$READER" ) >> "$ROOT/logs/reader.log" 2>&1 < /dev/null &
    READER_PID=$!

    echo "== (7/8) starting practice grading service on 127.0.0.1:$practice_port =="
    echo "2026-03-01T00:00:00+00:00" > "$ROOT/now.txt"
    ( exec env KEEL_PRACTICE_PORT="$practice_port" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_PROXY_URL="http://127.0.0.1:$proxy_port" \
        KEEL_TRACE_LOG="$ROOT/logs/traces.jsonl" \
        KEEL_SANDBOX_IMAGE="keel-runner:0.1" \
        KEEL_PRACTICE_NOW_FILE="$ROOT/now.txt" \
        setsid python3 "$PRACTICE" ) >> "$ROOT/logs/practice.log" 2>&1 < /dev/null &
    PRACTICE_PID=$!

    echo "== (8/8) starting learner app on 127.0.0.1:$app_port =="
    pkill -9 -f "next-server|node_modules/\.bin/next" 2>/dev/null || true
    ( cd "$APP_DIR" && exec env \
        KEEL_ENROLL_URL="http://127.0.0.1:$enroll_port" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_READER_URL="http://127.0.0.1:$reader_port" \
        KEEL_PRACTICE_URL="http://127.0.0.1:$practice_port" \
        KEEL_OFFLINE_AUTH_SECRET="$AUTH_SECRET" \
        KEEL_OFFLINE_AUTH_STORE="$ROOT/offline-auth-store.json" \
        setsid ./node_modules/.bin/next dev -p "$app_port" -H 127.0.0.1 ) \
        >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
    APP_PID=$!

    wait_ready "$FAKE_STRIPE_PID" "$fake_stripe_port" "fake stripe"
    wait_ready "$FAKE_JUDGE_PID" "$fake_judge_port" "fake judge"
    wait_ready "$PROXY_PID" "$proxy_port" "proxy"
    wait_ready "$ENROLL_PID" "$enroll_port" "enroll service"
    wait_ready "$READER_PID" "$reader_port" "reader"
    wait_ready "$PRACTICE_PID" "$practice_port" "practice service"
    wait_ready "$APP_PID" "$app_port" "learner app"
    curl -sf -o /dev/null --max-time 30 "http://127.0.0.1:$app_port/" || true

    cat > "$STATE_FILE" <<STATE
DB_PORT=$db_port
ENROLL_PORT=$enroll_port
FAKE_STRIPE_PORT=$fake_stripe_port
FAKE_JUDGE_PORT=$fake_judge_port
PROXY_PORT=$proxy_port
READER_PORT=$reader_port
PRACTICE_PORT=$practice_port
APP_PORT=$app_port
FAKE_STRIPE_PID=$FAKE_STRIPE_PID
FAKE_JUDGE_PID=$FAKE_JUDGE_PID
PROXY_PID=$PROXY_PID
ENROLL_PID=$ENROLL_PID
READER_PID=$READER_PID
PRACTICE_PID=$PRACTICE_PID
APP_PID=$APP_PID
STATE

    echo "== demo is UP (app :${app_port}, enroll :${enroll_port}, reader :${reader_port}, practice :${practice_port}, proxy :${proxy_port}) =="
}

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1"; shift
    if ( "$@" ) >/dev/null 2>&1; then
        echo "  [PASS] $name"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  [FAIL] $name" >&2
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

html_count() {
    local jar="$1" path="$2" needle="$3"
    if [ "$jar" = "-" ]; then
        curl -sf --max-time 30 "http://127.0.0.1:${APP_PORT}${path}"
    else
        curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:${APP_PORT}${path}"
    fi | grep -oF "$needle" | wc -l
}

action_id() {
    python3 - "$1" <<'PYEOF'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
names = re.findall(r'name="(\$ACTION_ID_[0-9a-f]+)"', html)
if not names:
    sys.exit(1)
print(names[0])
PYEOF
}

post_action() {
    local jar="$1" path="$2"; shift 2
    local args=() kv
    for kv in "$@"; do args+=(-F "$kv"); done
    curl -s --max-time 30 -o /dev/null -w "%{http_code} %{redirect_url}" \
        -b "$jar" -c "$jar" -X POST "http://127.0.0.1:$APP_PORT$path" "${args[@]}"
}

signup() {
    local jar="$1" name="$2" email="$3"
    curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT/sign-up" -o "$ROOT/su.html"
    local action pay
    action="$(action_id "$ROOT/su.html")" || return 1
    pay="$(post_action "$jar" /sign-up "$action=" "name=$name" "email=$email" "next=/units/3.2.1")"
    [ "${pay%% *}" = "303" ]
}

pay_enrollment() {
    local jar="$1"
    curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:$APP_PORT/map" -o "$ROOT/map.html"
    local action resp pay_url
    action="$(action_id "$ROOT/map.html")" || return 1
    resp="$(post_action "$jar" /map "$action=" "unit_id=3.2.1")"
    pay_url="${resp#* }"
    [ "${resp%% *}" = "303" ] || return 1
    curl -s --max-time 30 -o /dev/null -w "%{http_code}" -X POST "$pay_url" | grep -q 302
}

student_id_by_email() {
    psql_sql "SELECT id FROM students WHERE email = '$1';"
}

do_prove() {
    do_setup
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    APP="http://127.0.0.1:$APP_PORT"
    JAR_JESSE="$ROOT/jar-jesse.txt"
    JAR_KIM="$ROOT/jar-kim.txt"
    rm -f "$JAR_JESSE" "$JAR_KIM" "$ROOT"/*.html "$ROOT"/*.json 2>/dev/null || true

    echo
    echo "== proof 1: jesse signs up and views unit 3.2.1 practice section pre-payment =="
    if signup "$JAR_JESSE" "Jesse Okafor" "jesse@keel.test"; then
        check "jesse signs up via real form" true
    else
        check "jesse signs up via real form" false
    fi

    # Trigger lazy student bridge
    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/units/3.2.1" -o "$ROOT/unit-pre.html"
    JESSE_ID="$(student_id_by_email jesse@keel.test)"
    check "jesse has student row in database" [ -n "$JESSE_ID" ]

    check "practice workbench renders on unit 3.2.1" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "practice-workbench")" -ge 1

    check "retrieval drill renders on unit 3.2.1" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "retrieval-drill")" -ge 1

    check "pre-enrollment practice prompt visible" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "NOT ENROLLED")" -ge 1

    echo
    echo "== proof 2: jesse pays for unit 3.2.1 -> practice workbench active =="
    check "jesse pays via fake checkout" pay_enrollment "$JAR_JESSE"
    check "enrollment activated in database" \
        test "$(psql_sql "SELECT count(*) FROM enrollments WHERE student_id=$JESSE_ID AND unit_id='3.2.1';")" = "1"

    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/units/3.2.1" -o "$ROOT/unit-post.html"
    check "post-enrollment practice workbench has run button" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "Run the checks")" -ge 1
    check "whitelisted editable files tabs visible (schemas.py, extractor.py)" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "schemas.py")" -ge 1

    echo
    echo "== proof 3: submit base problem (unfilled) -> RED verdict rendered in UI =="
    COMP_DIR="$REPO_ROOT/content/units/phase-3/3.2.1/completion"
    python3 -c "
import json, sys
data = {
    'unit_id': '3.2.1',
    'files': {
        'schemas.py': open('$COMP_DIR/schemas.py').read(),
        'extractor.py': open('$COMP_DIR/extractor.py').read(),
    }
}
with open('$ROOT/sub-base.json', 'w') as f:
    json.dump(data, f)
"
    SUB1_CODE="$(curl -s --max-time 60 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/sub-base.json" \
        -o "$ROOT/sub1-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/attempt")"
    check "submitting base files returns HTTP 200" [ "$SUB1_CODE" = "200" ]

    check "sub1 result is fail (1 pass / 2 fail)" \
        python3 -c "
import json, sys
res = json.load(open('$ROOT/sub1-resp.json'))
assert res['passed'] is False
assert res['pass_count'] == 1
assert res['total_checks'] == 3
"
    check "attempt 1 recorded in database" \
        test "$(psql_sql "SELECT count(*) FROM practice_attempts WHERE student_id=$JESSE_ID;")" = "1"

    # Inspect rendered unit page HTML for attempt 1
    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/units/3.2.1" -o "$ROOT/unit-att1.html"
    check "rendered page shows completion attempt history" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "Practice attempt history (1)")" -ge 1
    check "rendered page shows 1 / 3 passing" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "1 / 3 passing")" -ge 1

    echo
    echo "== proof 4: submit worked-example solution (filled) -> GREEN verdict rendered in UI =="
    WE_DIR="$REPO_ROOT/content/units/phase-3/3.2.1/worked-example"
    python3 -c "
import json, sys
data = {
    'unit_id': '3.2.1',
    'files': {
        'schemas.py': open('$WE_DIR/schemas.py').read(),
        'extractor.py': open('$WE_DIR/extractor.py').read(),
    }
}
with open('$ROOT/sub-we.json', 'w') as f:
    json.dump(data, f)
"
    SUB2_CODE="$(curl -s --max-time 60 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/sub-we.json" \
        -o "$ROOT/sub2-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/attempt")"
    check "submitting worked-example files returns HTTP 200" [ "$SUB2_CODE" = "200" ]

    check "sub2 result is pass (3 pass / 0 fail)" \
        python3 -c "
import json, sys
res = json.load(open('$ROOT/sub2-resp.json'))
assert res['passed'] is True
assert res['pass_count'] == 3
assert res['total_checks'] == 3
"
    check "attempt 2 recorded in database (2 total attempts)" \
        test "$(psql_sql "SELECT count(*) FROM practice_attempts WHERE student_id=$JESSE_ID;")" = "2"

    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/units/3.2.1" -o "$ROOT/unit-att2.html"
    check "rendered page shows completion attempt history of 2 attempts" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "Practice attempt history (2)")" -ge 1
    check "rendered page shows passing attempt in history" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "3 / 3 passing")" -ge 1

    echo
    echo "== proof 5: submit strong retrieval drill answer -> PASS verdict & token budget decrease =="
    BUDGET_BEFORE="$(psql_sql "SELECT tokens_used FROM budgets WHERE student_id=$JESSE_ID;")"

    RET1_CODE="$(curl -s --max-time 30 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d '{
            "unit_id": "3.2.1",
            "seed_index": 0,
            "seed_prompt": "why free-text LLM output cannot be parsed reliably by downstream systems",
            "answer": "Downstream code requires rigid types and fields. Raw language model generations vary unpredictably with prose, markdown delimiters, and formatting errors that cause json decoding exceptions."
        }' \
        -o "$ROOT/ret1-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/retrieval/attempt")"
    check "submitting retrieval drill answer returns HTTP 200" [ "$RET1_CODE" = "200" ]

    check "retrieval 1 result is pass with feedback and evidence" \
        python3 -c "
import json, sys
res = json.load(open('$ROOT/ret1-resp.json'))
assert res['passed'] is True
assert len(res['feedback']) > 0
assert len(res['evidence']) > 0
assert res['tokens_charged'] > 0
"
    check "retrieval attempt 1 recorded in database" \
        test "$(psql_sql "SELECT count(*) FROM retrieval_attempts WHERE student_id=$JESSE_ID;")" = "1"

    BUDGET_AFTER="$(psql_sql "SELECT tokens_used FROM budgets WHERE student_id=$JESSE_ID;")"
    check "student budget charged tokens in database" [ "$BUDGET_AFTER" -gt "$BUDGET_BEFORE" ]

    echo
    echo "== proof 6: submit weak retrieval drill answer -> FAIL verdict =="
    RET2_CODE="$(curl -s --max-time 30 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d '{
            "unit_id": "3.2.1",
            "seed_index": 1,
            "seed_prompt": "the distinction between prompting an LLM for JSON and enforcing schema via grammar constraints",
            "answer": "fail_me: Prompting for JSON and grammar constraints are identical because the model reads English."
        }' \
        -o "$ROOT/ret2-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/retrieval/attempt")"
    check "submitting weak retrieval answer returns HTTP 200" [ "$RET2_CODE" = "200" ]

    check "retrieval 2 result is fail with honest feedback" \
        python3 -c "
import json, sys
res = json.load(open('$ROOT/ret2-resp.json'))
assert res['passed'] is False
assert len(res['feedback']) > 0
"
    check "retrieval attempt 2 recorded in database (2 total retrieval attempts)" \
        test "$(psql_sql "SELECT count(*) FROM retrieval_attempts WHERE student_id=$JESSE_ID;")" = "2"

    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/units/3.2.1" -o "$ROOT/unit-ret2.html"
    check "rendered page shows retrieval attempt history" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "Every drill answer you have given (2)")" -ge 1

    echo
    echo "== proof 9: spaced re-checks (+3d / +7d) surface on /me and clear from the drill =="

    # Clean slate for this choreography: earlier proofs passed several seeds at
    # T0; drop jesse's retrieval history so exactly one seed is scheduled.
    psql_sql "DELETE FROM events WHERE type='practice.retrieval_graded' AND payload->>'student_id'='$JESSE_ID';"
    psql_sql "DELETE FROM retrieval_attempts WHERE student_id=$JESSE_ID;"

    set_recheck_now() {
        printf '%s\n' "$1" > "$ROOT/now.txt"
    }

    ret_answer_file() {
        python3 - "$ROOT/ret-body.json" "$RET_PASS" <<'PYEOF'
import json, sys
seed = "why free-text LLM output cannot be parsed reliably by downstream systems"
answer = open(sys.argv[2]).read()
with open(sys.argv[1], "w") as f:
    json.dump({"unit_id": "3.2.1", "seed_index": 0, "seed_prompt": seed, "answer": answer}, f)
PYEOF
    }

    RET_PASS="$ROOT/ret-pass-answer.txt"
    printf 'Downstream programs need deterministic typed fields. Free-text model output varies with conversational phrasing, markdown fences and trailing prose, so parsing it with json.loads fails or writes garbage into the database.' > "$RET_PASS"

    set_recheck_now "2026-03-01T00:00:00+00:00"   # T0
    ret_answer_file
    RET_CODE="$(curl -s --max-time 30 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/ret-body.json" \
        -o "$ROOT/ret-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/retrieval/attempt")"
    check "jesse passes seed 0 at T0 over HTTP 200" [ "$RET_CODE" = "200" ]

    check "/me shows the spaced re-checks panel" \
        test "$(html_count "$JAR_JESSE" /me "spaced-rechecks")" -ge 1
    check "/me honest zero state right after pass (0 DUE)" \
        test "$(html_count "$JAR_JESSE" /me '0<!-- --> DUE NOW')" -ge 1
    check "unit page has no due badge before T+3" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "data-keel-drill-due")" -eq 0

    set_recheck_now "2026-03-03T00:00:00+00:00"   # T+2
    check "/me still 0 DUE at T+2" \
        test "$(html_count "$JAR_JESSE" /me '0<!-- --> DUE NOW')" -ge 1
    check "unit page still without the due marker at T+2" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "data-keel-drill-due")" -eq 0

    set_recheck_now "2026-03-04T00:00:00+00:00"   # T+3
    check "/me flips to 1 DUE at T+3" \
        test "$(html_count "$JAR_JESSE" /me '1<!-- --> DUE NOW')" -ge 1
    check "/me names the due seed" \
        test "$(html_count "$JAR_JESSE" /me "why free-text LLM output cannot be parsed reliably by downstream systems")" -ge 1
    check "/me links into the unit drill" \
        test "$(html_count "$JAR_JESSE" /me "Open drill")" -ge 1
    check "unit page marks the due drill question at T+3 (badge + notice)" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "data-keel-drill-due")" -eq 2

    ret_answer_file
    RET_CODE="$(curl -s --max-time 30 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/ret-body.json" \
        -o "$ROOT/ret-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/retrieval/attempt")"
    check "completing the +3d re-check returns HTTP 200" [ "$RET_CODE" = "200" ]
    check "the SAME drill attempt cleared the due state (/me back to 0 DUE)" \
        test "$(html_count "$JAR_JESSE" /me '0<!-- --> DUE NOW')" -ge 1
    check "unit page badge cleared after completing" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "data-keel-drill-due")" -eq 0
    check "attempt counted as the re-check in history (2 rows)" \
        test "$(psql_sql "SELECT count(*) FROM retrieval_attempts WHERE student_id=$JESSE_ID;")" = "2"

    set_recheck_now "2026-03-11T00:00:00+00:00"   # T+10
    check "/me flips to 1 DUE again at T+10 (+7d leg)" \
        test "$(html_count "$JAR_JESSE" /me '1<!-- --> DUE NOW')" -ge 1

    ret_answer_file
    curl -s --max-time 30 -b "$JAR_JESSE" -c "$JAR_JESSE" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/ret-body.json" \
        -o "$ROOT/ret-resp.json" \
        -w "%{http_code}" \
        "$APP/api/practice/retrieval/attempt" >/dev/null

    set_recheck_now "2099-01-01T00:00:00+00:00"   # far future
    check "after the +7d pass the seed is retired: /me stays 0 DUE forever" \
        test "$(html_count "$JAR_JESSE" /me '0<!-- --> DUE NOW')" -ge 1 && test "$(html_count "$JAR_JESSE" /me '1<!-- --> DUE NOW')" -eq 0
    check "retired seed never re-surfaces on the unit page" \
        test "$(html_count "$JAR_JESSE" /units/3.2.1 "data-keel-drill-due")" -eq 0

    echo
    echo "== proof 7: practice events do not unlock units or earn rebates =="
    check "/map still shows 0 / 2 gates cleared" \
        test "$(html_count "$JAR_JESSE" /map "0 / 2")" -ge 1
    check "unlocked_units table has zero rows for jesse" \
        test "$(psql_sql "SELECT count(*) FROM unlocked_units WHERE student_id=$JESSE_ID;")" = "0"
    check "rebates table has zero earned rebates for jesse" \
        test "$(psql_sql "SELECT count(*) FROM rebates WHERE student_id=$JESSE_ID AND status='earned';")" = "0"

    echo
    echo "== proof 8: unenrolled student (Kim) cannot submit practice checks or retrieval drills =="
    if signup "$JAR_KIM" "Kim Alvarez" "kim@keel.test"; then
        check "kim signs up without payment" true
    else
        check "kim signs up without payment" false
    fi

    # Trigger bridge
    curl -sf --max-time 30 -b "$JAR_KIM" "$APP/units/3.2.1" -o /dev/null
    KIM_ID="$(student_id_by_email kim@keel.test)"

    KIM_SUB_CODE="$(curl -s --max-time 30 -b "$JAR_KIM" -c "$JAR_KIM" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/sub-we.json" \
        -w "%{http_code}" \
        -o /dev/null \
        "$APP/api/practice/attempt")"
    check "unenrolled kim completion attempt rejected with HTTP 403" [ "$KIM_SUB_CODE" = "403" ]

    KIM_RET_CODE="$(curl -s --max-time 30 -b "$JAR_KIM" -c "$JAR_KIM" \
        -H "Content-Type: application/json" \
        -d '{
            "unit_id": "3.2.1",
            "seed_index": 0,
            "seed_prompt": "why free-text LLM output cannot be parsed reliably by downstream systems",
            "answer": "valid answer attempt"
        }' \
        -w "%{http_code}" \
        -o /dev/null \
        "$APP/api/practice/retrieval/attempt")"
    check "unenrolled kim retrieval attempt rejected with HTTP 403" [ "$KIM_RET_CODE" = "403" ]
    check "kim has zero rows in retrieval_attempts" \
        test "$(psql_sql "SELECT count(*) FROM retrieval_attempts WHERE student_id=$KIM_ID;")" = "0"

    echo
    echo "== proof 9: S3.4 adaptive routing rules (two-student exit proof) =="
    PASS_ANS="Downstream programs need deterministic typed fields. Free-text model output varies with conversational phrasing, markdown fences, and trailing prose, so parsing it with json.loads or string splits fails or writes garbage downstream."

    # Student 1: Maya (Fast Pass: clean sweep on first try -> worked example optional -> completion workbench)
    JAR_MAYA="$ROOT/jar-maya.txt"
    if signup "$JAR_MAYA" "Maya Lin" "maya@keel.test"; then
        check "maya signs up" true
    else
        check "maya signs up" false
    fi
    pay_enrollment "$JAR_MAYA"
    curl -sf --max-time 30 -b "$JAR_MAYA" "$APP/units/3.2.1" -o /dev/null
    MAYA_ID="$(student_id_by_email maya@keel.test)"

    # Maya passes all 5 seeds on first try
    for idx in 0 1 2 3 4; do
        curl -s --max-time 30 -b "$JAR_MAYA" -c "$JAR_MAYA" \
            -H "Content-Type: application/json" \
            -d "{\"unit_id\":\"3.2.1\",\"seed_index\":$idx,\"seed_prompt\":\"seed $idx prompt\",\"answer\":\"$PASS_ANS\"}" \
            "$APP/api/practice/retrieval/attempt" >/dev/null
    done

    curl -sf --max-time 30 -b "$JAR_MAYA" "$APP/units/3.2.1" -o "$ROOT/maya-unit.html"
    check "maya unit page shows FAST PASS ACTIVE" \
        test "$(html_count "$JAR_MAYA" /units/3.2.1 "SHORTER ROUTE")" -ge 1
    check "maya unit page shows worked example is OPTIONAL" \
        test "$(html_count "$JAR_MAYA" /units/3.2.1 "OPTIONAL")" -ge 1
    check "maya route API reports fast_pass" \
        test "$(curl -sf -H "X-Keel-App-Token: $APP_TOKEN" "http://127.0.0.1:$PRACTICE_PORT/practice/route?student_id=$MAYA_ID&unit=3.2.1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status'))")" = "fast_pass"

    # Student 2: Leo (Failure-route: fails drill -> scaffold review callout -> retry -> pass)
    JAR_LEO="$ROOT/jar-leo.txt"
    if signup "$JAR_LEO" "Leo Hayes" "leo@keel.test"; then
        check "leo signs up" true
    else
        check "leo signs up" false
    fi
    pay_enrollment "$JAR_LEO"
    curl -sf --max-time 30 -b "$JAR_LEO" "$APP/units/3.2.1" -o /dev/null
    LEO_ID="$(student_id_by_email leo@keel.test)"

    # Leo fails seed 1
    curl -s --max-time 30 -b "$JAR_LEO" -c "$JAR_LEO" \
        -H "Content-Type: application/json" \
        -d '{"unit_id":"3.2.1","seed_index":1,"seed_prompt":"why schema-constrained generation beats prompt-promised JSON","answer":"fail_me: prompt is enough"}' \
        "$APP/api/practice/retrieval/attempt" >/dev/null

    curl -sf --max-time 30 -b "$JAR_LEO" "$APP/units/3.2.1" -o "$ROOT/leo-unit-fail.html"
    check "leo unit page shows SCAFFOLD ROUTE ACTIVE" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "EXTRA PRACTICE ADDED")" -ge 1
    check "leo unit page marks worked example with RECOMMENDED REVIEW (SCAFFOLD)" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "WORTH RE-READING")" -ge 1
    check "leo unit page links to scaffold target file llm.py" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "GO BACK TO THE WORKED EXAMPLE")" -ge 1 \
        && test "$(html_count "$JAR_LEO" /units/3.2.1 "llm.py")" -ge 1

    # Leo passes all seeds (retrying seed 1)
    for idx in 0 1 2 3 4; do
        curl -s --max-time 30 -b "$JAR_LEO" -c "$JAR_LEO" \
            -H "Content-Type: application/json" \
            -d "{\"unit_id\":\"3.2.1\",\"seed_index\":$idx,\"seed_prompt\":\"seed $idx prompt\",\"answer\":\"$PASS_ANS\"}" \
            "$APP/api/practice/retrieval/attempt" >/dev/null
    done

    # Leo passes completion problem
    curl -s --max-time 60 -b "$JAR_LEO" -c "$JAR_LEO" \
        -H "Content-Type: application/json" \
        -d @"$ROOT/sub-we.json" \
        "$APP/api/practice/attempt" >/dev/null

    curl -sf --max-time 30 -b "$JAR_LEO" "$APP/units/3.2.1" -o "$ROOT/leo-unit-pass.html"
    check "leo unit page shows ROUTE COMPLETE" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "ROUTE COMPLETE")" -ge 1
    check "leo unit page links to Build deliverable" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "Start the deliverable")" -ge 1

    echo
    echo "== proof 10: unenrolled kim's schedule and route are honestly empty =="
    check "kim's /me reports 0 DUE and lists no seeds" \
        test "$(html_count "$JAR_KIM" /me '0<!-- --> DUE NOW')" -ge 1 \
        && test "$(html_count "$JAR_KIM" /me "Open drill")" -eq 0
    check "kim's route API reports enrolled: false" \
        test "$(curl -sf -H "X-Keel-App-Token: $APP_TOKEN" "http://127.0.0.1:$PRACTICE_PORT/practice/route?student_id=$KIM_ID&unit=3.2.1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('enrolled'))")" = "False"

    echo
    echo "== proof 11: concierge teach/guard mode switch & turn persistence =="
    # Leo is route-completed: asks concierge in build context -> guard mode
    local leo_cask
    leo_cask="$(curl -sf -b "$JAR_LEO" -c "$JAR_LEO" \
        -H "Content-Type: application/json" \
        -d '{"unit_id":"3.2.1","question":"Can you write the deliverable for me?"}' \
        "$APP/api/concierge/ask")"
    check "leo concierge ask returns guard mode" \
        test "$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('mode'))" "$leo_cask")" = "guard"
    check "leo concierge reply includes unblocking contract" \
        test "$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print('unblock' in d.get('answer','').lower() or 'deliverable' in d.get('answer','').lower())" "$leo_cask")" = "True"

    # Kim (unenrolled) -> HTTP 403
    local kim_status
    kim_status="$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR_KIM" -c "$JAR_KIM" \
        -H "Content-Type: application/json" \
        -d '{"unit_id":"3.2.1","question":"How do schemas work?"}' \
        "$APP/api/concierge/ask")"
    check "unenrolled kim concierge ask returns HTTP 403" \
        test "$kim_status" = "403"

    # Leo unit page renders concierge section with GUARD MODE badge
    # Greps the question box's id rather than the heading copy: 3.2.1's lesson is a
    # unit script and authors its own heading, and the box only renders for a
    # signed-in enrolled student, so this proves more than a string match did.
    check "leo unit page renders the ask-about-this-unit panel" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "concierge-question")" -ge 1
    check "leo unit page renders GUARD MODE badge" \
        test "$(html_count "$JAR_LEO" /units/3.2.1 "WORKS IT THROUGH WITH YOU")" -ge 1

    echo
    echo "== practice demo summary: $PASS_COUNT passed, $FAIL_COUNT failed =="
    [ "$FAIL_COUNT" -eq 0 ] || exit 1
}

do_teardown_inner() {
    # shellcheck disable=SC1090
    [ -f "$STATE_FILE" ] && . "$STATE_FILE"
    for pid in "${APP_PID:-}" "${PRACTICE_PID:-}" "${READER_PID:-}" "${ENROLL_PID:-}" "${PROXY_PID:-}" "${FAKE_JUDGE_PID:-}" "${FAKE_STRIPE_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        fi
    done
    pkill -9 -f "fake_stripe|fake_judge_upstream|proxy/server\.py|enroll/server\.py|reader/server\.py|practice/server\.py|next-server|node_modules/\.bin/next" 2>/dev/null || true
    sleep 1
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$ROOT"
}

do_teardown() {
    do_teardown_inner
    if pgrep -f "enroll/server.py|fake_stripe.py|reader/server.py|practice/server.py|fake_judge_upstream.py|proxy/server.py" >/dev/null 2>&1; then
        echo "FAIL: demo daemons survived the kill" >&2
        pgrep -af "enroll/server.py|fake_stripe.py|reader/server.py|practice/server.py|fake_judge_upstream.py|proxy/server.py" >&2 || true
        exit 1
    fi
    echo "== practice demo torn down; containers, dirs and daemons gone =="
}

case "${1:-}" in
    setup) do_setup ;;
    prove) do_prove ;;
    teardown) do_teardown ;;
    *) echo "usage: $0 {setup|prove|teardown}" >&2; exit 2 ;;
esac
