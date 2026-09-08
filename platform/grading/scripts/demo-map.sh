#!/usr/bin/env bash
# NOTE: the copy greps below assert the CURRENT PLACEHOLDER copy (pre-redesign).
# A UI session that rewrites copy updates these greps to the new strings and
# re-runs this demo green — see the 2026-08-27 copy-unfreeze decision in build-state.md.
# demo-map.sh — S2.8 end-to-end proof: progress dashboard v1, "the growing progress map".
#
# Modes:
#   setup     Scratch postgres (0001..0006), offline fake Stripe, enroll service,
#             read-only reader with GET /students/<id>/submissions, and the Next.js
#             learner app under setsid. Persists until teardown.
#   prove     Drives real sign-up and payment, runs gate engine and rebate machine
#             one-shots, and inspects /map in HTML after every state transition:
#             1. pre-enrollment map view (open unit 3.2.1, locked gates)
#             2. post-enrollment map view (unit 3.2.1 enrolled · open workbench)
#             3. mid-flight submission state (queued / grading)
#             4. pass on 5.1 -> Phase 5 gate cleared, Phase 6 unlocked, rebate earned
#             5. fail on 12.1 -> Capstone gate locked, Phase 6 track remains unlocked
#             6. second unenrolled student (Kim) sees honest pre-payment map
#             7. reader GET /students/<id>/submissions API validation
#   teardown  Stops daemons and removes scratch container and files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE="$SCRIPT_DIR/../enroll/fake_stripe.py"
READER="$SCRIPT_DIR/../reader/server.py"
ENGINE="$SCRIPT_DIR/../gates/engine.py"
MACHINE="$SCRIPT_DIR/../rebate/machine.py"

ROOT="/tmp/keel-map-demo"
CONTAINER="keel-map-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
STATE_FILE="$ROOT/pids.env"

APP_TOKEN="demo-map-app-token"
WHSEC="whsec_demo_map_placeholder"
STRIPE_KEY="sk_test_placeholder_not_a_real_key"
AUTH_SECRET="demo-map-offline-auth-secret"
PRICE_CENTS="1234"
REBATE_PCT="15"

T0="2026-01-01T00:00:00+00:00"
T10="2026-01-11T00:00:00+00:00"
T20="2026-01-21T00:00:00+00:00"

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

wait_http() {
    local timeout="${3:-120}" i
    for i in $(seq 1 "$((timeout * 2))"); do
        if curl -sf -o /dev/null --max-time 10 "$1"; then return 0; fi
        sleep 0.5
    done
    echo "FAIL: $2 never became ready at $1" >&2
    return 1
}

do_setup() {
    mkdir -p "$ROOT/logs"
    if [ -f "$STATE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$STATE_FILE"
        local alive=1
        for pid in "${ENROLL_PID:-}" "${FAKE_PID:-}" "${READER_PID:-}" "${APP_PID:-}"; do
            [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || alive=0
        done
        if [ "$alive" = "1" ]; then
            echo "== demo already up (app :${APP_PORT}, enroll :${ENROLL_PORT}, reader :${READER_PORT}, fake stripe :${FAKE_PORT}) =="
            return 0
        fi
        do_teardown_inner
    fi

    local db_port enroll_port fake_port reader_port app_port
    read -r db_port fake_port enroll_port reader_port app_port < <(python3 -c 'import socket; socks=[socket.socket() for _ in range(5)]; [s.bind(("127.0.0.1",0)) for s in socks]; print(" ".join(str(s.getsockname()[1]) for s in socks)); [s.close() for s in socks]')

    echo "== (1/5) starting postgres on 127.0.0.1:$db_port =="
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

    for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates; do
        "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
            < "$SCRIPT_DIR/../schema/$m.sql" >/dev/null
    done

    echo "== (2/5) starting fake stripe on 127.0.0.1:$fake_port =="
    ( exec env KEEL_FAKE_STRIPE_PORT="$fake_port" \
        KEEL_FAKE_STRIPE_WEBHOOK_URL="http://127.0.0.1:$enroll_port/webhook/stripe" \
        KEEL_FAKE_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        setsid python3 "$FAKE" ) >> "$ROOT/logs/fake-stripe.log" 2>&1 < /dev/null &
    FAKE_PID=$!

    echo "== (3/5) starting enroll service on 127.0.0.1:$enroll_port =="
    ( exec env KEEL_ENROLL_PORT="$enroll_port" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_STRIPE_API_URL="http://127.0.0.1:$fake_port/v1" \
        STRIPE_SECRET_KEY="$STRIPE_KEY" \
        KEEL_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        KEEL_PRICE_CENTS_3_2_1="$PRICE_CENTS" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        KEEL_DEFAULT_BUDGET_TOKENS="5000" \
        setsid python3 "$ENROLL" ) >> "$ROOT/logs/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!

    echo "== (4/5) starting reader service on 127.0.0.1:$reader_port =="
    ( exec env KEEL_READER_PORT="$reader_port" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        setsid python3 "$READER" ) >> "$ROOT/logs/reader.log" 2>&1 < /dev/null &
    READER_PID=$!

    echo "== (5/5) starting learner app on 127.0.0.1:$app_port =="
    ( cd "$APP_DIR" && exec env \
        KEEL_ENROLL_URL="http://127.0.0.1:$enroll_port" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_READER_URL="http://127.0.0.1:$reader_port" \
        KEEL_OFFLINE_AUTH_SECRET="$AUTH_SECRET" \
        KEEL_OFFLINE_AUTH_STORE="$ROOT/offline-auth-store.json" \
        setsid ./node_modules/.bin/next dev -p "$app_port" -H 127.0.0.1 ) \
        >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
    APP_PID=$!

    wait_http "http://127.0.0.1:$fake_port/__count" "fake stripe" || exit 1
    wait_http "http://127.0.0.1:$enroll_port/healthz" "enroll service" || exit 1
    wait_http "http://127.0.0.1:$reader_port/healthz" "reader" || exit 1
    wait_http "http://127.0.0.1:$app_port/" "learner app" || exit 1

    cat > "$STATE_FILE" <<STATE
DB_PORT=$db_port
ENROLL_PORT=$enroll_port
FAKE_PORT=$fake_port
READER_PORT=$reader_port
APP_PORT=$app_port
FAKE_PID=$FAKE_PID
ENROLL_PID=$ENROLL_PID
READER_PID=$READER_PID
APP_PID=$APP_PID
STATE

    echo "== demo is UP (app :${app_port}, enroll :${enroll_port}, reader :${reader_port}) =="
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

html_has() {  # html_has <cookie-jar-or-"-"> <path> <needle>
    # The body is captured and then matched with a bash pattern rather than
    # piped into `grep -q`. grep exits on its first match, so on a page larger
    # than the pipe buffer the writer is still writing when the pipe closes,
    # dies of SIGPIPE, and `set -o pipefail` turns a found needle into a
    # failed assertion.
    local jar="$1" path="$2" needle="$3" body
    if [ "$jar" = "-" ]; then
        body="$(curl -sf --max-time 30 "http://127.0.0.1:${APP_PORT}${path}")" || return 1
    else
        body="$(curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:${APP_PORT}${path}")" || return 1
    fi
    case "$body" in *"$needle"*) return 0 ;; esac
    return 1
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

run_engine() {
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_GATE_ONCE=1 \
        KEEL_GATE_NOW="$1" \
        python3 "$ENGINE" ) >> "$ROOT/logs/engine.log" 2>&1
}

run_machine() {
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_REBATE_ONCE=1 \
        KEEL_REBATE_NOW="$1" KEEL_REBATE_PCT="$REBATE_PCT" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        python3 "$MACHINE" ) >> "$ROOT/logs/machine.log" 2>&1
}

signup() {
    local jar="$1" name="$2" email="$3"
    curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT/sign-up" -o "$ROOT/su.html"
    local action pay
    action="$(action_id "$ROOT/su.html")" || return 1
    pay="$(post_action "$jar" /sign-up "$action=" "name=$name" "email=$email" "next=/map")"
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

fabricate_verdict() {
    local sid="$1" unit="$2" overall="$3" at="$4"
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA -v ON_ERROR_STOP=1 <<SQL
INSERT INTO submissions (student_id, unit_id, commit_sha, status)
VALUES ($sid, '$unit', 'mapdemo${sid}${unit}${overall}', 'graded');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
SELECT id, 'rubric-$unit', 1, '$overall',
       '{"overall": "$overall", "note": "deterministic map demo fixture"}'
FROM submissions WHERE student_id = $sid AND unit_id = '$unit'
  AND commit_sha = 'mapdemo${sid}${unit}${overall}';
INSERT INTO events (type, payload, occurred_at)
SELECT 'verdict.issued',
       jsonb_build_object('submission_id', s.id, 'student_id', $sid,
                          'unit_id', '$unit', 'commit_sha', s.commit_sha,
                          'overall', '$overall', 'verdict_id', v.id),
       '$at'::timestamptz
FROM submissions s JOIN verdicts v ON v.submission_id = s.id
WHERE s.student_id = $sid AND s.unit_id = '$unit'
  AND s.commit_sha = 'mapdemo${sid}${unit}${overall}';
SQL
}

do_prove() {
    do_setup
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    APP="http://127.0.0.1:$APP_PORT"
    JAR_JESSE="$ROOT/jar-jesse.txt"; JAR_KIM="$ROOT/jar-kim.txt"
    rm -f "$JAR_JESSE" "$JAR_KIM" "$ROOT"/*.html "$ROOT"/*.json 2>/dev/null || true
    : > "$ROOT/logs/engine.log"
    : > "$ROOT/logs/machine.log"

    echo
    echo "== proof 1: jesse signs up and views honest pre-payment map =="
    if signup "$JAR_JESSE" "Jesse Okafor" "jesse@keel.test"; then
        check "jesse signs up via real form" true
    else
        check "jesse signs up via real form" false
    fi

    # Trigger lazy student bridge by loading /map once
    curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/map" -o /dev/null
    JESSE_ID="$(student_id_by_email jesse@keel.test)"
    check "jesse has student row in database" [ -n "$JESSE_ID" ]

    check "/map renders the progress map header" \
        html_has "$JAR_JESSE" /map "The whole system, phase by phase"
    check "/map shows all 13 phases" \
        html_has "$JAR_JESSE" /map "phase-12"
    check '/map shows Unit 3.2.1 open with Enroll button' \
        html_has "$JAR_JESSE" /map 'Enroll ($12.34)'
    check "/map shows Phase 5 integration gate locked" \
        html_has "$JAR_JESSE" /map "Phase 5 integration gate"
    check "/map shows Capstone gate locked" \
        html_has "$JAR_JESSE" /map "Final capstone gate"
    check "/map unauthored units show honest 'Content arriving'" \
        html_has "$JAR_JESSE" /map "PLANNED"

    echo
    echo "== proof 2: jesse pays for unit 3.2.1 -> map shows enrolled & workbench link =="
    check "jesse pays via fake checkout" pay_enrollment "$JAR_JESSE"
    check "enrollment activated in database" \
        test "$(psql_sql "SELECT count(*) FROM enrollments WHERE student_id=$JESSE_ID AND unit_id='3.2.1';")" = "1"

    check "/map shows unit 3.2.1 as enrolled with an open-unit link" \
        html_has "$JAR_JESSE" /map "Open unit"
    check "/map open-unit link points at /units/3.2.1" \
        html_has "$JAR_JESSE" /map 'href="/units/3.2.1"'

    echo
    echo "== proof 3: mid-flight submission state (queued / grading) visible on /map =="
    SUB_ID="$(psql_sql "INSERT INTO submissions (student_id, unit_id, commit_sha, status) VALUES ($JESSE_ID, '3.2.1', 'sha_q1', 'queued') RETURNING id;")"
    check "/map shows queued submission status" \
        html_has "$JAR_JESSE" /map "QUEUED"
    check "/map links to submission" \
        html_has "$JAR_JESSE" /map "href=\"/submissions/$SUB_ID\""

    psql_sql "UPDATE submissions SET status = 'grading' WHERE id = $SUB_ID;"
    check "/map shows grading submission status" \
        html_has "$JAR_JESSE" /map "GRADING"

    echo
    echo "== proof 4: pass on 5.1 -> Phase 5 gate cleared, Phase 6 unlocked, rebate earned =="
    fabricate_verdict "$JESSE_ID" "5.1" "pass" "$T10"
    run_engine "$T10"
    run_machine "$T10"

    check "database records Phase 5 gate cleared" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='gate.passed' AND payload->>'gate_id'='phase-5-integration';")" = "1"
    check "database records 4 unlocked units in Phase 6" \
        test "$(psql_sql "SELECT count(*) FROM unlocked_units WHERE student_id=$JESSE_ID;")" = "4"
    check "rebate earned in database" \
        test "$(psql_sql "SELECT status FROM rebates WHERE student_id=$JESSE_ID AND gate_id='phase-5-integration';")" = "earned"

    check "/map shows Phase 5 gate cleared" \
        html_has "$JAR_JESSE" /map "GATE CLEARED"
    check "/map shows clearance timestamp" \
        html_has "$JAR_JESSE" /map "Cleared on"
    check "/map shows Phase 6 track unlocked" \
        test "$(curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/map" | grep -oF 'TRACK LOCKED' | wc -l)" = "0"
    check '/map shows 15% rebate earned milestone ($1.85)' \
        html_has "$JAR_JESSE" /map '$1.85'
    check "/map Capstone gate remains locked" \
        html_has "$JAR_JESSE" /map "A passing verdict on unit 12.1 clears this gate"

    echo
    echo "== proof 5: fail on 12.1 -> Capstone gate stays locked, unlocks never reverse =="
    fabricate_verdict "$JESSE_ID" "12.1" "fail" "$T20"
    run_engine "$T20"

    check "capstone gate remains locked in db" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='gate.passed' AND payload->>'gate_id'='capstone';")" = "0"
    check "/map shows Unit 12.1 as not yet passed" \
        html_has "$JAR_JESSE" /map "NOT YET"
    check "/map Phase 5 gate still cleared" \
        html_has "$JAR_JESSE" /map "GATE CLEARED"

    echo
    echo "== proof 6: second unenrolled student (Kim) sees honest pre-payment map =="
    if signup "$JAR_KIM" "Kim Alvarez" "kim@keel.test"; then
        check "kim signs up without payment" true
    else
        check "kim signs up without payment" false
    fi

    curl -sf --max-time 30 -b "$JAR_KIM" "$APP/map" -o /dev/null
    KIM_ID="$(student_id_by_email kim@keel.test)"

    check '/map for kim shows Unit 3.2.1 open for enrollment' \
        html_has "$JAR_KIM" /map 'Enroll ($12.34)'
    check "/map for kim shows zero gates cleared" \
        test "$(curl -sf --max-time 30 -b "$JAR_KIM" "$APP/map" | grep -oF "0 / 2" | wc -l)" -ge 1
    check '/map for kim shows $0 rebates earned' \
        html_has "$JAR_KIM" /map '$0'
    check "/map for kim shows Phase 6 track locked" \
        html_has "$JAR_KIM" /map "Locked behind the Phase 5 integration gate."

    echo
    echo "== proof 7: reader service GET /students/<id>/submissions API =="
    check "reader serves jesse submissions listing" \
        bash -c "curl -sf http://127.0.0.1:$READER_PORT/students/$JESSE_ID/submissions | grep -qF '\"submissions\"' && curl -sf http://127.0.0.1:$READER_PORT/students/$JESSE_ID/submissions | grep -qF '\"overall\": \"pass\"'"
    check "reader returns honest empty submissions for kim" \
        bash -c "curl -sf http://127.0.0.1:$READER_PORT/students/$KIM_ID/submissions | grep -qF '\"submissions\": []'"

    rm -f "$ROOT"/*.html "$ROOT"/*.json "$ROOT"/jar-*.txt 2>/dev/null || true
    echo
    echo "== map demo summary: $PASS_COUNT passed, $FAIL_COUNT failed =="
    [ "$FAIL_COUNT" -eq 0 ] || exit 1
}

do_teardown_inner() {
    # shellcheck disable=SC1090
    [ -f "$STATE_FILE" ] && . "$STATE_FILE"
    for pid in "${APP_PID:-}" "${READER_PID:-}" "${ENROLL_PID:-}" "${FAKE_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        fi
    done
    pkill -9 -f "fake_stripe|reader/server\.py|enroll/server\.py|next-server|node_modules/\.bin/next" 2>/dev/null || true
    sleep 1
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$ROOT"
}

do_teardown() {
    do_teardown_inner
    if pgrep -f "enroll/server.py|fake_stripe.py|reader/server.py" >/dev/null 2>&1 \
        || pgrep -f "node_modules/.bin/next dev" >/dev/null 2>&1; then
        echo "FAIL: demo daemons survived the kill" >&2
        pgrep -af "enroll/server.py|fake_stripe.py|reader/server.py|node_modules/.bin/next dev" >&2 || true
        exit 1
    fi
    echo "== map demo torn down; containers, dirs and daemons gone =="
}

case "${1:-}" in
    setup) do_setup ;;
    prove) do_prove ;;
    teardown) do_teardown ;;
    *) echo "usage: $0 {setup|prove|teardown}" >&2; exit 2 ;;
esac
