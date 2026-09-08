#!/usr/bin/env bash
# NOTE: the copy greps below assert the CURRENT PLACEHOLDER copy (pre-redesign).
# A UI session that rewrites copy updates these greps to the new strings and
# re-runs this demo green — see the 2026-08-27 copy-unfreeze decision in build-state.md.
# demo-gates.sh — S2.7 end-to-end proof: a student's /me shows gate status
# driven by verdict events through the engine, the reader, and the REAL
# rebate machine, with the real learner app rendering it.
#
# Modes:
#   setup     Scratch postgres (0001..0006), the offline fake Stripe, the
#             enroll service, the read-only reader, and the learner app dev
#             server under setsid so they survive this script. Persists
#             until teardown. No real credential anywhere; auth runs in
#             offline mode.
#   prove     Run setup if needed, then drive the real HTTP surface: sign-up
#             and payment through the actual app forms (the enroll webhook
#             writes the REAL enrollment.activated event), the gate engine
#             one-shot at deterministic clock points (KEEL_GATE_NOW) turning
#             that enrollment into engine-emitted gate.pledged events and a
#             worker-shaped passing verdict into gate.passed + unlock state,
#             the rebate machine one-shot earning from those engine-emitted
#             events (no faked gate rows anywhere), and /me + the reader
#             after every step. A second student who never pays proves the
#             enrollment coupling, and a late fail verdict proves unlocks
#             never reverse. Exit 0 only if every assertion holds.
#   teardown  Stop everything and remove the scratch container and dir.
#
# The verdict rows/events inserted here are the deterministic offline fake
# for the verdict pipeline (shaped exactly as worker.py writes them); every
# consumer downstream of them is real.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE="$SCRIPT_DIR/../enroll/fake_stripe.py"
READER="$SCRIPT_DIR/../reader/server.py"
ENGINE="$SCRIPT_DIR/../gates/engine.py"
MACHINE="$SCRIPT_DIR/../rebate/machine.py"

ROOT="/tmp/keel-gates-demo"
CONTAINER="keel-gates-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
STATE_FILE="$ROOT/pids.env"

# Test-mode placeholders; no real key is ever used or echoed.
APP_TOKEN="demo-app-token"
WHSEC="whsec_demo_placeholder"
STRIPE_KEY="sk_test_placeholder_not_a_real_key"
AUTH_SECRET="demo-offline-auth-secret"
PRICE_CENTS="1234"           # $12.34 unit price AND default price for the
                             # rebate amount: 15% of 1234 = 185 = $1.85
REBATE_PCT="15"

# Deterministic clock:
T0="2026-01-01T00:00:00+00:00"    # payment / pledge time
T10="2026-01-11T00:00:00+00:00"   # verified passage (inside the window)
T20="2026-01-21T00:00:00+00:00"   # late fail verdict (after the unlock)

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

psql_sql() {  # one -tA session
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA <<< "$1"
}

wait_http() {  # wait_http <url> <name> [timeout_s]
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
        echo "== stale state file; cleaning and re-standing ==" >&2
        do_teardown_inner || true
    fi

    echo "== starting postgres + schema 0001..0006 =="
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    DB_PORT="$(free_port)"
    "$DOCKER" run -d --name "$CONTAINER" \
        -e POSTGRES_USER="$DB_USER" -e POSTGRES_PASSWORD=smoke -e POSTGRES_DB="$DB_NAME" \
        -p "127.0.0.1:$DB_PORT:5432" postgres:16-alpine >/dev/null
    for i in $(seq 1 60); do
        "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select 1;" >/dev/null 2>&1 && break
        sleep 1
    done
    for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates 0006_gates; do
        "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
            < "$SCRIPT_DIR/../schema/$m.sql" >/dev/null
    done

    FAKE_PORT="$(free_port)"
    ENROLL_PORT="$(free_port)"
    READER_PORT="$(free_port)"
    APP_PORT="$(free_port)"

    echo "== starting fake stripe :$FAKE_PORT =="
    ( exec env KEEL_FAKE_STRIPE_PORT="$FAKE_PORT" \
        KEEL_FAKE_STRIPE_WEBHOOK_URL="http://127.0.0.1:$ENROLL_PORT/webhook/stripe" \
        KEEL_FAKE_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        setsid python3 "$FAKE" ) >> "$ROOT/logs/fake-stripe.log" 2>&1 < /dev/null &
    FAKE_PID=$!

    echo "== starting enroll service :$ENROLL_PORT (stripe -> fake) =="
    ( exec env KEEL_ENROLL_PORT="$ENROLL_PORT" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_STRIPE_API_URL="http://127.0.0.1:$FAKE_PORT/v1" \
        STRIPE_SECRET_KEY="$STRIPE_KEY" \
        KEEL_STRIPE_WEBHOOK_SECRET="$WHSEC" \
        KEEL_PRICE_CENTS_3_2_1="$PRICE_CENTS" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        KEEL_DEFAULT_BUDGET_TOKENS="5000" \
        setsid python3 "$ENROLL" ) >> "$ROOT/logs/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!

    echo "== starting reader :$READER_PORT (read-only gate state) =="
    ( exec env KEEL_READER_PORT="$READER_PORT" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        setsid python3 "$READER" ) >> "$ROOT/logs/reader.log" 2>&1 < /dev/null &
    READER_PID=$!

    echo "== starting learner app :$APP_PORT (offline auth, enroll + reader wired) =="
    if pgrep -f "node_modules/.bin/next dev" >/dev/null 2>&1; then
        echo "FAIL: a next dev server is already running (Next refuses a second one):" >&2
        pgrep -af "node_modules/.bin/next dev" >&2 || true
        exit 1
    fi
    ( cd "$APP_DIR" && exec env \
        KEEL_ENROLL_URL="http://127.0.0.1:$ENROLL_PORT" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_READER_URL="http://127.0.0.1:$READER_PORT" \
        KEEL_OFFLINE_AUTH_SECRET="$AUTH_SECRET" \
        KEEL_OFFLINE_AUTH_STORE="$ROOT/offline-auth-store.json" \
        setsid ./node_modules/.bin/next dev -p "$APP_PORT" -H 127.0.0.1 ) \
        >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
    APP_PID=$!

    wait_http "http://127.0.0.1:$FAKE_PORT/__count" "fake stripe" || exit 1
    wait_http "http://127.0.0.1:$ENROLL_PORT/healthz" "enroll service" || exit 1
    wait_http "http://127.0.0.1:$READER_PORT/healthz" "reader" || exit 1
    wait_http "http://127.0.0.1:$APP_PORT/" "learner app" || exit 1

    printf 'FAKE_PID=%s\nFAKE_PORT=%s\nENROLL_PID=%s\nENROLL_PORT=%s\nREADER_PID=%s\nREADER_PORT=%s\nAPP_PID=%s\nAPP_PORT=%s\nAPP_TOKEN=%s\nWHSEC=%s\nPRICE_CENTS=%s\nAUTH_SECRET=%s\n' \
        "$FAKE_PID" "$FAKE_PORT" "$ENROLL_PID" "$ENROLL_PORT" \
        "$READER_PID" "$READER_PORT" \
        "$APP_PID" "$APP_PORT" "$APP_TOKEN" "$WHSEC" "$PRICE_CENTS" "$AUTH_SECRET" > "$STATE_FILE"

    cat <<SUMMARY

== gates demo READY (persists until teardown) ==
   app         : http://127.0.0.1:$APP_PORT
   your page   : http://127.0.0.1:$APP_PORT/me
   enroll svc  : http://127.0.0.1:$ENROLL_PORT/healthz
   reader      : http://127.0.0.1:$READER_PORT/healthz
   logs        : $ROOT/logs/

   prove: bash $SCRIPT_DIR/demo-gates.sh prove
   teardown: bash $SCRIPT_DIR/demo-gates.sh teardown
SUMMARY
}

PASS_COUNT=0
FAIL_COUNT=0
check() {  # check <name> <cmd...>
    local name="$1"; shift
    if ( "$@" ) >/dev/null 2>&1; then
        echo "PASS: $name"; PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "FAIL: $name"; FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

html_has() {  # html_has <cookie-jar-or-"-"> <path> <needle>
    # The body is captured and then matched with a bash pattern rather than
    # piped into `grep -q`. grep exits on its first match, so on a page larger
    # than the pipe buffer the writer is still writing when the pipe closes,
    # dies of SIGPIPE, and `set -o pipefail` turns a found needle into a
    # failed assertion.
    local jar="$1" body
    if [ "$jar" = "-" ]; then
        body="$(curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT$2")" || return 1
    else
        body="$(curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:$APP_PORT$2")" || return 1
    fi
    case "$body" in *"$3"*) return 0 ;; esac
    return 1
}

action_id() {  # action_id <html-file>
    python3 - "$1" <<'EOF'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
names = re.findall(r'name="(\$ACTION_ID_[0-9a-f]+)"', html)
if not names:
    sys.exit(1)
print(names[0])
EOF
}

post_action() {  # post_action <jar> <path> <field=value>... (first is the action id)
    local jar="$1" path="$2"; shift 2
    local args=() kv
    for kv in "$@"; do args+=(-F "$kv"); done
    curl -s --max-time 30 -o /dev/null -w "%{http_code} %{redirect_url}" \
        -b "$jar" -c "$jar" -X POST "http://127.0.0.1:$APP_PORT$path" "${args[@]}"
}

run_engine() {  # run_engine <KEEL_GATE_NOW>
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_GATE_ONCE=1 \
        KEEL_GATE_NOW="$1" \
        python3 "$ENGINE" ) >> "$ROOT/logs/engine.log" 2>&1
}

run_machine() {  # run_machine <KEEL_REBATE_NOW>
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_REBATE_ONCE=1 \
        KEEL_REBATE_NOW="$1" KEEL_REBATE_PCT="$REBATE_PCT" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        python3 "$MACHINE" ) >> "$ROOT/logs/machine.log" 2>&1
}

signup() {  # signup <jar> <name> <email>; exits nonzero on failure
    local jar="$1" name="$2" email="$3"
    curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT/sign-up" -o "$ROOT/su.html"
    local action pay
    action="$(action_id "$ROOT/su.html")" || return 1
    pay="$(post_action "$jar" /sign-up "$action=" "name=$name" "email=$email" "next=/me")"
    [ "${pay%% *}" = "303" ]
}

pay_enrollment() {  # pay_enrollment <jar>; drives /me enroll action -> fake pay -> return
    local jar="$1"
    curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:$APP_PORT/me" -o "$ROOT/me.html"
    local action resp pay_url
    action="$(action_id "$ROOT/me.html")" || return 1
    resp="$(post_action "$jar" /me "$action=" "unit_id=3.2.1")"
    pay_url="${resp#* }"
    [ "${resp%% *}" = "303" ] || return 1
    curl -s --max-time 30 -o /dev/null -w "%{http_code}" -X POST "$pay_url" | grep -q 302
}

student_id_by_email() {  # -> numeric students.id
    psql_sql "SELECT id FROM students WHERE email = '$1';"
}

fabricate_verdict() {  # fabricate_verdict <student_id> <unit> <overall> <occurred_at>
    # The deterministic offline fake for the verdict pipeline: submissions
    # row + verdicts row + worker.py's exact verdict.issued payload.
    local sid="$1" unit="$2" overall="$3" at="$4"
    # -i: the heredoc SQL reaches psql over stdin. ON_ERROR_STOP: a failed
    # insert is a loud nonzero exit, never a silently missing verdict.
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA -v ON_ERROR_STOP=1 <<SQL
INSERT INTO submissions (student_id, unit_id, commit_sha, status)
VALUES ($sid, '$unit', 'demo${sid}${unit}${overall}', 'graded');
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
SELECT id, 'rubric-$unit', 1, '$overall',
       '{"overall": "$overall", "note": "deterministic demo fixture"}'
FROM submissions WHERE student_id = $sid AND unit_id = '$unit'
  AND commit_sha = 'demo${sid}${unit}${overall}';
INSERT INTO events (type, payload, occurred_at)
SELECT 'verdict.issued',
       jsonb_build_object('submission_id', s.id, 'student_id', $sid,
                          'unit_id', '$unit', 'commit_sha', s.commit_sha,
                          'overall', '$overall', 'verdict_id', v.id),
       '$at'::timestamptz
FROM submissions s JOIN verdicts v ON v.submission_id = s.id
WHERE s.student_id = $sid AND s.unit_id = '$unit'
  AND s.commit_sha = 'demo${sid}${unit}${overall}';
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
    echo "== proof 1: jesse signs up and pays through the real app =="
    if signup "$JAR_JESSE" "Jesse Okafor" "jesse@keel.test"; then
        check "jesse signs up through the real form" true
    else
        check "jesse signs up through the real form" false
    fi
    check "jesse pays via the fake checkout" pay_enrollment "$JAR_JESSE"
    JESSE_ID="$(student_id_by_email jesse@keel.test)"
    check "the enroll webhook wrote the real enrollment.activated event" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='enrollment.activated' AND payload->>'student_id'='$JESSE_ID';")" = "1"

    echo
    echo "== proof 2: engine turns that enrollment into gate.pledged; machine pledges =="
    run_engine "$T0"
    check "engine emitted both pledges (jesse, one per rebate rule)" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='gate.pledged' AND payload->>'student_id'='$JESSE_ID';")" = "2"
    run_machine "$T0"
    check "rebate machine pledged 2 pending rows from engine events" \
        test "$(psql_sql "SELECT count(*) || ':' || min(amount_cents) FROM rebates WHERE student_id=$JESSE_ID AND status='pending';")" = "2:185"
    check "/me shows the Gates section with both gates locked" \
        html_has "$JAR_JESSE" /me "Milestone gates" \
        && test "$(curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/me" | grep -oF '>LOCKED<' | wc -l)" = "2"
    check "/me locked copy names what clears the gate (content-as-data)" \
        html_has "$JAR_JESSE" /me "A passing verdict on unit 5.1 clears this gate"
    check "/me locked copy names the capstone unit" \
        html_has "$JAR_JESSE" /me "A passing verdict on unit 12.1 clears this gate"
    check "/me locked copy says what the phase gate unlocks" \
        html_has "$JAR_JESSE" /me "Passing unlocks units 6.1, 6.2, 6.3, 6.4."
    check "/me rebate section shows two pending rows" \
        test "$(curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/me" | grep -oF '>PENDING<' | wc -l)" = "2"

    echo
    echo "== proof 3: worker-shaped passing verdict -> engine unlocks + gate.passed -> machine earns =="
    fabricate_verdict "$JESSE_ID" "5.1" "pass" "$T10"
    run_engine "$T10"
    check "engine unlocked the phase 6 track for jesse" \
        test "$(psql_sql "SELECT count(*) FROM unlocked_units WHERE student_id=$JESSE_ID;")" = "4"
    check "unit.unlocked events on the spine, cause-linked" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='unit.unlocked' AND payload->>'student_id'='$JESSE_ID';")" = "4"
    check "engine emitted exactly one gate.passed per the S2.6 contract" \
        test "$(psql_sql "SELECT (payload->>'gate_id') || ':' || (payload->>'unit_id') || ':' || (payload->>'passed_at') FROM events WHERE type='gate.passed';")" = "phase-5-integration:5.1:2026-01-11T00:00:00+00:00"
    run_machine "$T10"
    check "rebate machine EARNS from the engine's own gate.passed" \
        test "$(psql_sql "SELECT status FROM rebates WHERE student_id=$JESSE_ID AND gate_id='phase-5-integration';")" = "earned"
    check "the earn references the engine's event seq" \
        test "$(psql_sql "SELECT earned_event_seq = (SELECT seq FROM events WHERE type='gate.passed' AND payload->>'gate_id'='phase-5-integration') FROM rebates WHERE student_id=$JESSE_ID AND gate_id='phase-5-integration';")" = "t"
    check "capstone rebate still pending" \
        test "$(psql_sql "SELECT status FROM rebates WHERE student_id=$JESSE_ID AND gate_id='capstone';")" = "pending"
    check "reader serves the student gate state" \
        bash -c "curl -sf http://127.0.0.1:$READER_PORT/students/$JESSE_ID/gates | grep -qF '\"gates_passed\"' && curl -sf http://127.0.0.1:$READER_PORT/students/$JESSE_ID/gates | grep -qF 'phase-5-integration'"
    check "/me phase-5 gate now shows cleared with a date" \
        bash -c "curl -sf --max-time 30 -b '$JAR_JESSE' '$APP/me' | grep -qF '>CLEARED<' && curl -sf --max-time 30 -b '$JAR_JESSE' '$APP/me' | grep -qF 'Cleared on'"
    check "/me names the unlocked units after the clear" \
        html_has "$JAR_JESSE" /me "Units 6.1, 6.2, 6.3, 6.4 unlocked."
    check "/me capstone gate still locked" \
        test "$(curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/me" | grep -oF '>LOCKED<' | wc -l)" = "1"
    check "/me rebate section shows the earned phase-5 row" \
        test "$(curl -sf --max-time 30 -b "$JAR_JESSE" "$APP/me" | grep -oF '>EARNED<' | wc -l)" = "1"

    echo
    echo "== proof 4: engine cursor reset + replay changes nothing =="
    psql_sql "UPDATE gate_cursor SET last_seq = 0 WHERE consumer = 'gate-engine';" >/dev/null
    run_engine "$T10"
    check "replay adds no unlock rows, events, or pledges" \
        test "$(psql_sql "SELECT (SELECT count(*) FROM unlocked_units WHERE student_id=$JESSE_ID) || ':' || (SELECT count(*) FROM events WHERE type IN ('gate.pledged','gate.passed','unit.unlocked'));")" = "4:7"
    check "earned state survives the replay" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='rebate.earned';")" = "1"

    echo
    echo "== proof 5: unenrolled student's verdict is ignored =="
    if signup "$JAR_KIM" "Kim Alvarez" "kim@keel.test"; then
        check "kim signs up (and does not pay)" true
    else
        check "kim signs up (and does not pay)" false
    fi
    # kim's students row is created lazily by the auth bridge on her first
    # authenticated /me load (jesse's was bridged by the payment flow's /me
    # fetch); load it once so the id lookup sees the bridged row.
    curl -sf --max-time 30 -b "$JAR_KIM" "$APP/me" -o /dev/null
    KIM_ID="$(student_id_by_email kim@keel.test)"
    fabricate_verdict "$KIM_ID" "5.1" "pass" "$T10"
    run_engine "$T10"
    check "no unlock, no gate event for kim (enrollment coupling)" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE payload->>'student_id'='$KIM_ID' AND type IN ('gate.pledged','gate.passed','unit.unlocked');")" = "0" \
        && test "$(psql_sql "SELECT count(*) FROM unlocked_units WHERE student_id=$KIM_ID;")" = "0"
    check "/me for kim shows both gates locked and no rebate ledger" \
        test "$(curl -sf --max-time 30 -b "$JAR_KIM" "$APP/me" | grep -oF '>LOCKED<' | wc -l)" = "2" \
        && test "$(curl -sf --max-time 30 -b "$JAR_KIM" "$APP/me" | grep -oF 'Completion rebates' | wc -l)" = "0"

    echo
    echo "== proof 6: a later fail verdict never reverses the unlock =="
    fabricate_verdict "$JESSE_ID" "12.1" "fail" "$T20"
    run_engine "$T20"
    check "jesse's unlock rows untouched by the fail" \
        test "$(psql_sql "SELECT count(*) FROM unlocked_units WHERE student_id=$JESSE_ID;")" = "4"
    check "capstone still locked on /me; phase-5 still cleared" \
        bash -c "curl -sf --max-time 30 -b '$JAR_JESSE' '$APP/me' | grep -qF '>CLEARED<' && test \"\$(curl -sf --max-time 30 -b '$JAR_JESSE' '$APP/me' | grep -cF '>LOCKED<')\" = 1"
    check "no fail verdict ever produced a gate event" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='gate.passed' AND payload->>'unit_id'='12.1';")" = "0"

    rm -f "$ROOT"/*.html "$ROOT"/*.json "$ROOT"/jar-*.txt 2>/dev/null || true
    echo
    echo "== proof summary: $PASS_COUNT passed, $FAIL_COUNT failed =="
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
    sleep 1
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$ROOT"
}

do_teardown() {
    do_teardown_inner
    if pgrep -f "enroll/server.py|fake_stripe.py|reader/server.py" >/dev/null 2>&1 \
        || pgrep -f "next dev -p " >/dev/null 2>&1; then
        echo "FAIL: demo daemons survived the kill" >&2
        pgrep -af "enroll/server.py|fake_stripe.py|reader/server.py|next dev" >&2 || true
        exit 1
    fi
    echo "== demo torn down; containers, dirs and daemons gone =="
}

case "${1:-}" in
    setup) do_setup ;;
    prove) do_prove ;;
    teardown) do_teardown ;;
    *) echo "usage: $0 {setup|prove|teardown}" >&2; exit 2 ;;
esac
