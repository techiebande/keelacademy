#!/usr/bin/env bash
# NOTE: the copy greps below assert the CURRENT PLACEHOLDER copy (pre-redesign).
# A UI session that rewrites copy updates these greps to the new strings and
# re-runs this demo green — see the 2026-08-27 copy-unfreeze decision in build-state.md.
# demo-rebate.sh — S2.6 end-to-end proof: a student's /me shows rebate
# status driven by gate events through the real learner app.
#
# Modes:
#   setup     Scratch postgres (0001..0005), the offline fake Stripe, the
#             enroll service, and the learner app dev server under setsid so
#             they survive this script. Persists until teardown. No real
#             credential anywhere; auth runs in offline mode.
#   prove     Run setup if needed, then drive the real HTTP surface: sign-up
#             and payment through the actual app forms, the S2.7 gate events
#             (gate.pledged / gate.passed) faked deterministically onto the
#             events spine, the rebate machine run one-shot at deterministic
#             clock points (KEEL_REBATE_NOW, no sleeps), and /me after every
#             transition: pending -> earned -> paid, plus an expired window
#             for a second student and a replayed gate event that changes
#             nothing. Exit 0 only if every assertion holds.
#   teardown  Stop everything and remove the scratch container and dir.
#
# The gate events inserted here are the published contract S2.7's gate engine
# will emit; nothing in the machine knows who wrote them.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE="$SCRIPT_DIR/../enroll/fake_stripe.py"
MACHINE="$SCRIPT_DIR/../rebate/machine.py"

ROOT="/tmp/keel-rebate-demo"
CONTAINER="keel-rebate-demo-pg"
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

# Deterministic clock (mirrors smoke-rebate-checks.py):
T0="2026-01-01T00:00:00+00:00"    # pledge time
T10="2026-01-11T00:00:00+00:00"   # verified passage (inside the 30-day window)
T40="2026-02-10T00:00:00+00:00"   # past the window

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
        for pid in "${ENROLL_PID:-}" "${FAKE_PID:-}" "${APP_PID:-}"; do
            [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || alive=0
        done
        if [ "$alive" = "1" ]; then
            echo "== demo already up (app :${APP_PORT}, enroll :${ENROLL_PORT}, fake stripe :${FAKE_PORT}) =="
            return 0
        fi
        echo "== stale state file; cleaning and re-standing ==" >&2
        do_teardown_inner || true
    fi

    echo "== starting postgres + schema 0001..0005 =="
    "$DOCKER" rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
    DB_PORT="$(free_port)"
    "$DOCKER" run -d --name "$CONTAINER" \
        -e POSTGRES_USER="$DB_USER" -e POSTGRES_PASSWORD=smoke -e POSTGRES_DB="$DB_NAME" \
        -p "127.0.0.1:$DB_PORT:5432" postgres:16-alpine >/dev/null
    for i in $(seq 1 60); do
        "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "select 1;" >/dev/null 2>&1 && break
        sleep 1
    done
    for m in 0001_init 0002_intake 0003_budgets 0004_enrollments 0005_rebates; do
        "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
            < "$SCRIPT_DIR/../schema/$m.sql" >/dev/null
    done

    FAKE_PORT="$(free_port)"
    ENROLL_PORT="$(free_port)"
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

    echo "== starting learner app :$APP_PORT (offline auth, enroll wired) =="
    if pgrep -f "node_modules/.bin/next dev" >/dev/null 2>&1; then
        echo "FAIL: a next dev server is already running (Next refuses a second one):" >&2
        pgrep -af "node_modules/.bin/next dev" >&2 || true
        exit 1
    fi
    ( cd "$APP_DIR" && exec env \
        KEEL_ENROLL_URL="http://127.0.0.1:$ENROLL_PORT" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_OFFLINE_AUTH_SECRET="$AUTH_SECRET" \
        KEEL_OFFLINE_AUTH_STORE="$ROOT/offline-auth-store.json" \
        setsid ./node_modules/.bin/next dev -p "$APP_PORT" -H 127.0.0.1 ) \
        >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
    APP_PID=$!

    wait_http "http://127.0.0.1:$FAKE_PORT/__count" "fake stripe" || exit 1
    wait_http "http://127.0.0.1:$ENROLL_PORT/healthz" "enroll service" || exit 1
    wait_http "http://127.0.0.1:$APP_PORT/" "learner app" || exit 1

    printf 'FAKE_PID=%s\nFAKE_PORT=%s\nENROLL_PID=%s\nENROLL_PORT=%s\nAPP_PID=%s\nAPP_PORT=%s\nAPP_TOKEN=%s\nWHSEC=%s\nPRICE_CENTS=%s\nAUTH_SECRET=%s\n' \
        "$FAKE_PID" "$FAKE_PORT" "$ENROLL_PID" "$ENROLL_PORT" \
        "$APP_PID" "$APP_PORT" "$APP_TOKEN" "$WHSEC" "$PRICE_CENTS" "$AUTH_SECRET" > "$STATE_FILE"

    cat <<SUMMARY

== rebate demo READY (persists until teardown) ==
   app         : http://127.0.0.1:$APP_PORT
   your page   : http://127.0.0.1:$APP_PORT/me
   enroll svc  : http://127.0.0.1:$ENROLL_PORT/healthz
   logs        : $ROOT/logs/

   prove: bash $SCRIPT_DIR/demo-rebate.sh prove
   teardown: bash $SCRIPT_DIR/demo-rebate.sh teardown
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

emit_gate_event() {  # emit_gate_event <type> <json-payload> <occurred_at>
    "$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA \
        -c "INSERT INTO events (type, payload, occurred_at) VALUES ('$1', '$2'::jsonb, '$3'::timestamptz);" >/dev/null
}

run_machine() {  # run_machine <KEEL_REBATE_NOW>
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_REBATE_ONCE=1 \
        KEEL_REBATE_NOW="$1" KEEL_REBATE_PCT="$REBATE_PCT" \
        KEEL_PRICE_CENTS_DEFAULT="$PRICE_CENTS" \
        python3 "$MACHINE" ) >> "$ROOT/logs/machine.log" 2>&1
}

signup() {  # signup <jar> <name> <email>; echoes nothing, exits nonzero on failure
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

do_prove() {
    do_setup
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    APP="http://127.0.0.1:$APP_PORT"
    JAR_PAT="$ROOT/jar-pat.txt"; JAR_RILEY="$ROOT/jar-riley.txt"
    rm -f "$JAR_PAT" "$JAR_RILEY" "$ROOT"/*.html 2>/dev/null || true
    : > "$ROOT/logs/machine.log"

    echo
    echo "== proof 1: two students sign up and pay through the real app =="
    if signup "$JAR_PAT" "Pat Newman" "pat@keel.test"; then
        check "pat signs up through the real form" true
    else
        check "pat signs up through the real form" false
    fi
    check "pat pays via the fake checkout" pay_enrollment "$JAR_PAT"
    PAT_ID="$(student_id_by_email pat@keel.test)"
    if signup "$JAR_RILEY" "Riley Chen" "riley@keel.test"; then
        check "riley signs up through the real form" true
    else
        check "riley signs up through the real form" false
    fi
    check "riley pays via the fake checkout" pay_enrollment "$JAR_RILEY"
    RILEY_ID="$(student_id_by_email riley@keel.test)"
    check "/me shows no rebate section before any pledge" \
        test "$(curl -sf --max-time 30 -b "$JAR_PAT" "$APP/me" | grep -cF 'Completion rebates')" = "0"

    echo
    echo "== proof 2: gate.pledged -> pending on /me =="
    emit_gate_event gate.pledged \
        "{\"student_id\": $PAT_ID, \"gate_id\": \"phase-5-integration\", \"unit_id\": \"5.1\", \"window_days\": 30}" "$T0"
    run_machine "$T0"
    check "one pending rebate row, amount 15% of \$12.34 = \$1.85" \
        test "$(psql_sql "SELECT status || ':' || amount_cents FROM rebates WHERE student_id = $PAT_ID;")" = "pending:185"
    check "/me renders the rebate section with the gate name" \
        html_has "$JAR_PAT" /me "Phase 5 integration gate"
    check "/me shows the pending chip and the window" \
        html_has "$JAR_PAT" /me ">PENDING<"
    check "/me names the window end" html_has "$JAR_PAT" /me "Window open until"
    check "/me says the credit needs a passing verdict" \
        html_has "$JAR_PAT" /me "Pass the gate before then"

    echo
    echo "== proof 3: verified gate.passed inside the window -> earned on /me =="
    emit_gate_event gate.passed \
        "{\"student_id\": $PAT_ID, \"gate_id\": \"phase-5-integration\", \"unit_id\": \"5.1\", \"passed_at\": \"$T10\"}" "$T10"
    run_machine "$T10"
    check "rebate earned with the deterministic timestamp" \
        test "$(psql_sql "SELECT status || ':' || to_char(earned_at, 'YYYY-MM-DD') FROM rebates WHERE student_id = $PAT_ID;")" = "earned:2026-01-11"
    check "exactly one rebate.earned event on the spine" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='rebate.earned';")" = "1"
    check "/me shows the earned chip and the amount" \
        bash -c "curl -sf --max-time 30 -b '$JAR_PAT' '$APP/me' | grep -qF '>EARNED<' && curl -sf --max-time 30 -b '$JAR_PAT' '$APP/me' | grep -qF '\$1.85'"
    check "/me is honest that a person issues the refund" \
        html_has "$JAR_PAT" /me "We refund it to your card by hand"

    echo
    echo "== proof 4: replayed gate event changes nothing (earn-once) =="
    emit_gate_event gate.passed \
        "{\"student_id\": $PAT_ID, \"gate_id\": \"phase-5-integration\", \"unit_id\": \"5.1\", \"passed_at\": \"$T10\"}" "$T10"
    run_machine "$T10"
    check "still exactly one pending->earned transition" \
        test "$(psql_sql "SELECT count(*) FROM rebate_transitions WHERE to_status='earned';")" = "1"
    check "still exactly one rebate.earned event" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='rebate.earned';")" = "1"
    check "/me still shows exactly one earned rebate row" \
        test "$(curl -sf --max-time 30 -b "$JAR_PAT" "$APP/me" | grep -cF 'Phase 5 integration gate')" = "1"

    echo
    echo "== proof 5: riley's window elapses -> expired on /me (timed transition) =="
    emit_gate_event gate.pledged \
        "{\"student_id\": $RILEY_ID, \"gate_id\": \"phase-5-integration\", \"unit_id\": \"5.1\", \"window_days\": 30}" "$T0"
    run_machine "$T0"
    run_machine "$T40"
    check "riley's rebate expired by the deterministic sweep" \
        test "$(psql_sql "SELECT status FROM rebates WHERE student_id = $RILEY_ID;")" = "expired"
    check "expiry is event-sourced" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='rebate.expired';")" = "1"
    check "/me shows the expired chip and the honest copy" \
        bash -c "curl -sf --max-time 30 -b '$JAR_RILEY' '$APP/me' | grep -qF '>EXPIRED<' && curl -sf --max-time 30 -b '$JAR_RILEY' '$APP/me' | grep -qF 'without a passing verdict'"

    echo
    echo "== proof 6: runbook payout mark -> paid on /me (ledger only) =="
    PAT_REBATE="$(psql_sql "SELECT id FROM rebates WHERE student_id = $PAT_ID;")"
    MARK_RC=0
    ( exec env KEEL_DB_CMD="$DB_CMD_PLAIN" KEEL_REBATE_NOW="$T40" \
        KEEL_REBATE_REASON="stripe refund re_demo_001" KEEL_REBATE_ACTOR="founder" \
        python3 "$MACHINE" --mark-paid "$PAT_REBATE" ) >> "$ROOT/logs/machine.log" 2>&1 \
        || MARK_RC=$?
    check "mark-paid exits 0" test "$MARK_RC" -eq 0
    check "transition carries who/what/when" \
        test "$(psql_sql "SELECT actor || ':' || reason FROM rebate_transitions WHERE to_status='paid';")" = "founder:stripe refund re_demo_001"
    check "/me shows the paid chip and the refunded amount" \
        bash -c "curl -sf --max-time 30 -b '$JAR_PAT' '$APP/me' | grep -qF '>PAID<' && curl -sf --max-time 30 -b '$JAR_PAT' '$APP/me' | grep -qF 'to your payment method on'"
    check "/me is the final state: pat paid, riley expired" \
        bash -c "curl -sf --max-time 30 -b '$JAR_PAT' '$APP/me' | grep -qF '>PAID<' && curl -sf --max-time 30 -b '$JAR_RILEY' '$APP/me' | grep -qF '>EXPIRED<'"

    echo
    echo "== proof 7: the profile API carries the ledger (auditability) =="
    curl -sf --max-time 30 -H "X-Keel-App-Token: $APP_TOKEN" \
        "http://127.0.0.1:$ENROLL_PORT/students/$PAT_ID/profile" -o "$ROOT/profile.json"
    check "profile JSON lists the paid rebate with amount and dates" \
        bash -c "grep -qF '\"status\": \"paid\"' '$ROOT/profile.json' && grep -qF '\"amount_cents\": 185' '$ROOT/profile.json' && grep -qF '\"paid_at\"' '$ROOT/profile.json'"
    check "every transition row names an actor, reason, and time" \
        test "$(psql_sql "SELECT count(*) FROM rebate_transitions WHERE actor='' OR reason='' OR occurred_at IS NULL;")" = "0"

    rm -f "$ROOT"/*.html "$ROOT"/*.json "$ROOT"/jar-*.txt 2>/dev/null || true
    echo
    echo "== proof summary: $PASS_COUNT passed, $FAIL_COUNT failed =="
    [ "$FAIL_COUNT" -eq 0 ] || exit 1
}

do_teardown_inner() {
    # shellcheck disable=SC1090
    [ -f "$STATE_FILE" ] && . "$STATE_FILE"
    for pid in "${APP_PID:-}" "${ENROLL_PID:-}" "${FAKE_PID:-}"; do
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
    if pgrep -f "enroll/server.py|fake_stripe.py" >/dev/null 2>&1 \
        || pgrep -f "next dev -p " >/dev/null 2>&1; then
        echo "FAIL: demo daemons survived the kill" >&2
        pgrep -af "enroll/server.py|fake_stripe.py|next dev" >&2 || true
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
