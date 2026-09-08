#!/usr/bin/env bash
# NOTE: the copy greps below assert the CURRENT PLACEHOLDER copy (pre-redesign).
# A UI session that rewrites copy updates these greps to the new strings and
# re-runs this demo green — see the 2026-08-27 copy-unfreeze decision in build-state.md.
# demo-enroll.sh — S2.5 end-to-end proof: sign-up -> checkout -> webhook ->
# enrollment, through the real learner app.
#
# Modes:
#   setup     Scratch postgres (0001..0004) seeded with alice + one graded
#             submission, the read-only reader, the enroll service, the
#             offline fake Stripe, and the learner app dev server — all
#             under setsid so they survive this script. Persists until
#             teardown. No real credential anywhere: the Stripe key and the
#             webhook secret are test placeholders, auth runs in its offline
#             mode, and the app talks to the fake checkout page.
#   prove     Run setup if needed, then drive the real HTTP surface: sign-up
#             through the actual server-action form posts, the auth gate on
#             /me and verdict pages, cross-account 404, checkout through the
#             app's enroll action into the fake hosted pay page, the signed
#             webhook, the enrolled /me, and the webhook replay. Exit 0 only
#             if every assertion holds.
#   teardown  Stop everything and remove the scratch container and dir.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
READER="$SCRIPT_DIR/../reader/server.py"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
FAKE="$SCRIPT_DIR/../enroll/fake_stripe.py"

ROOT="/tmp/keel-enroll-demo"
CONTAINER="keel-enroll-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
STATE_FILE="$ROOT/pids.env"

# Test-mode placeholders; no real key is ever used or echoed.
APP_TOKEN="demo-app-token"
WHSEC="whsec_demo_placeholder"
STRIPE_KEY="sk_test_placeholder_not_a_real_key"
AUTH_SECRET="demo-offline-auth-secret"
PRICE_CENTS="1234"

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
            echo "== demo already up (app :${APP_PORT}, enroll :${ENROLL_PORT}, fake stripe :${FAKE_PORT}) =="
            return 0
        fi
        echo "== stale state file; cleaning and re-standing ==" >&2
        do_teardown_inner || true
    fi

    echo "== starting postgres + schema 0001..0005 + alice's graded submission =="
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
    psql_sql "
INSERT INTO students (email, display_name) VALUES ('alice@keel.test', 'Alice');
INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, status)
SELECT id, '3.2.1', 'aa11bb22cc33', 'https://example/keel-3.2.1-alice', 'graded'
FROM students WHERE email = 'alice@keel.test';
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
SELECT id, 'rubric-3.2.1', 1, 'pass', '{\"overall\": \"pass\"}'
FROM submissions WHERE commit_sha = 'aa11bb22cc33';" >/dev/null

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
        KEEL_DEFAULT_BUDGET_TOKENS="5000" \
        setsid python3 "$ENROLL" ) >> "$ROOT/logs/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!

    echo "== starting read-only reader :$READER_PORT =="
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
        KEEL_READER_URL="http://127.0.0.1:$READER_PORT" \
        KEEL_ENROLL_URL="http://127.0.0.1:$ENROLL_PORT" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
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
        "$FAKE_PID" "$FAKE_PORT" "$ENROLL_PID" "$ENROLL_PORT" "$READER_PID" "$READER_PORT" \
        "$APP_PID" "$APP_PORT" "$APP_TOKEN" "$WHSEC" "$PRICE_CENTS" "$AUTH_SECRET" > "$STATE_FILE"

    cat <<SUMMARY

== enrollment demo READY (persists until teardown) ==
   app         : http://127.0.0.1:$APP_PORT
   your page   : http://127.0.0.1:$APP_PORT/me        (sign-up -> enroll -> pay)
   fake stripe : http://127.0.0.1:$FAKE_PORT          (hosted pay page)
   enroll svc  : http://127.0.0.1:$ENROLL_PORT/healthz
   logs        : $ROOT/logs/

   Browser path: /sign-up -> create account -> Enroll for \$12.34 -> Pay -> enrolled.
   alice@keel.test also works and shows her existing graded submission.

   teardown: bash $SCRIPT_DIR/demo-enroll.sh teardown
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

# Extract the progressive-enhancement action id from a rendered form:
# Next injects <input type="hidden" name="$ACTION_ID_..."> for no-JS posts.
action_id() {  # action_id <html-file> <form-field-prefix>
    python3 - "$1" "$2" <<'EOF'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
names = re.findall(r'name="(\$ACTION_ID_[0-9a-f]+)"', html)
if not names:
    sys.exit(1)
print(names[0])
EOF
}

post_action() {  # post_action <jar> <path> <field=value>... (first is the action id)
    # The rendered forms carry encType="multipart/form-data", so the no-JS
    # posts mirror that exactly with curl -F.
    local jar="$1" path="$2"; shift 2
    local args=()
    local kv
    for kv in "$@"; do args+=(-F "$kv"); done
    curl -s --max-time 30 -o /dev/null -w "%{http_code} %{redirect_url}" \
        -b "$jar" -c "$jar" -X POST "http://127.0.0.1:$APP_PORT$path" "${args[@]}"
}

do_prove() {
    do_setup
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    APP="http://127.0.0.1:$APP_PORT"
    JAR_NEW="$ROOT/jar-new.txt"; JAR_ALICE="$ROOT/jar-alice.txt"
    rm -f "$JAR_NEW" "$JAR_ALICE"

    echo
    echo "== proof 1: the gate — signed-out visitors cannot reach private pages =="
    CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$APP/me")"
    LOC="$(curl -s -o /dev/null -w "%{redirect_url}" --max-time 30 "$APP/me")"
    check "/me redirects signed-out to sign-in" test "$CODE" = "307" -a "${LOC#*next=}" = "%2Fme"
    CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$APP/submissions/1")"
    check "/submissions/1 redirects signed-out" test "$CODE" = "307"
    check "signed-out header shows Sign in" html_has - "/" ">Sign in<"

    echo
    echo "== proof 2: sign-up through the real form (no-JS action post) =="
    curl -sf --max-time 30 "$APP/sign-up" -o "$ROOT/signup.html"
    ACTION="$(action_id "$ROOT/signup.html" sign-up)" \
        || { echo "FAIL: no action id in sign-up form" >&2; exit 1; }
    RESP="$(post_action "$JAR_NEW" /sign-up "$ACTION=" "name=Pat Newman" "email=pat@keel.test" "next=/me")"
    check "sign-up posts, answers 303 to /me" \
        test "${RESP%% *}" = "303" -a "${RESP#* }" = "$APP/me"
    check "sign-up set the session cookie" grep -q "keel_session" "$JAR_NEW"
    check "/me greets the new account" html_has "$JAR_NEW" /me "pat@keel.test"
    check "/me links the new grading record" html_has "$JAR_NEW" /me "Grading record #2"
    check "/me shows the honest empty submissions state" html_has "$JAR_NEW" /me "No submissions yet"

    echo
    echo "== proof 3: an existing pusher signs up and claims their history =="
    # alice@keel.test has a students row (and one graded submission) from
    # pushing, but no managed identity yet. Signing up with that email must
    # claim the existing row instead of forking a second one.
    ACTION="$(action_id "$ROOT/signup.html" sign-up)" \
        || { echo "FAIL: no action id in sign-up form" >&2; exit 1; }
    RESP="$(post_action "$JAR_ALICE" /sign-up "$ACTION=" "name=Alice" "email=alice@keel.test" "next=/me")"
    check "sign-up with a pusher email answers 303 to /me" \
        test "${RESP%% *}" = "303" -a "${RESP#* }" = "$APP/me"
    check "/me links alice to grading record #1" html_has "$JAR_ALICE" /me "Grading record #1"
    check "/me lists her graded submission" html_has "$JAR_ALICE" /me "#1"
    check "no forked student row" \
        test "$(psql_sql "SELECT count(*) FROM students WHERE email='alice@keel.test';")" = "1"
    check "alice's row now carries the external auth id" \
        test "$(psql_sql "SELECT external_auth_id IS NOT NULL FROM students WHERE email='alice@keel.test';")" = "t"

    echo
    echo "== proof 4: verdict page is owner-gated =="
    # The h1 text is split by React node comments, so assert on the stable
    # status attribute the S2.4 banner carries instead.
    check "owner sees her verdict page" html_has "$JAR_ALICE" /submissions/1 'data-keel-status="graded"' 
    CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -b "$JAR_NEW" "$APP/submissions/1")"
    check "another account's cookie gets 404 on alice's verdict" test "$CODE" = "404"
    check "verdict page names the owning account" html_has "$JAR_ALICE" /submissions/1 "alice@keel.test"

    echo
    echo "== proof 5: checkout through the app's enroll action -> fake pay -> webhook =="
    check "/me offers Enroll for the configured price" html_has "$JAR_NEW" /me "Enroll for \$12.34"
    curl -sf --max-time 30 -b "$JAR_NEW" "$APP/me" -o "$ROOT/me.html"
    ACTION="$(action_id "$ROOT/me.html" enroll)" \
        || { echo "FAIL: no action id on the enroll button" >&2; exit 1; }
    RESP="$(post_action "$JAR_NEW" /me "$ACTION=" "unit_id=3.2.1")"
    PAY_URL="${RESP#* }"
    check "enroll action redirects to the fake checkout page" \
        test "${RESP%% *}" = "303" -a "${PAY_URL#http://127.0.0.1:$FAKE_PORT/pay/}" != "$PAY_URL"
    CS_ID="${PAY_URL##*/}"
    curl -sf --max-time 30 "$PAY_URL" -o "$ROOT/pay.html"
    check "hosted pay page shows the price and session id" \
        bash -c "grep -qF 'Pay \$12.34' '$ROOT/pay.html' && grep -qF '$CS_ID' '$ROOT/pay.html'"
    curl -s --max-time 30 -o /dev/null -w "%{http_code} %{redirect_url}" -X POST "$PAY_URL" \
        > "$ROOT/pay-redirect.txt"
    RETURN_URL="$(cut -d" " -f2- "$ROOT/pay-redirect.txt")"
    check "pay redirects to the app's return page" \
        test "$(cut -d" " -f1 "$ROOT/pay-redirect.txt")" = "302" \
             -a "${RETURN_URL#"$APP/checkout/return?session_id=$CS_ID"}" != "$RETURN_URL"
    check "return page confirms enrollment" \
        html_has "$JAR_NEW" "/checkout/return?session_id=$CS_ID&unit=3.2.1" "You are enrolled in unit 3.2.1"
    check "/me shows the enrolled chip" html_has "$JAR_NEW" /me ">ENROLLED<"
    check "/me shows the provisioned budget" html_has "$JAR_NEW" /me "of 5,000 used"
    check "exactly one enrollment row in the grading store" \
        test "$(psql_sql "SELECT count(*) FROM enrollments;")" = "1"
    check "exactly one enrollment.activated event" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='enrollment.activated';")" = "1"
    check "budget provisioned" \
        test "$(psql_sql "SELECT tokens_cap FROM budgets b JOIN students s ON s.id=b.student_id WHERE s.email='pat@keel.test';")" = "5000"

    echo
    echo "== proof 6: a replayed webhook must not double-enroll (app stack) =="
    python3 - "$ENROLL_PORT" "$WHSEC" "$CS_ID" > "$ROOT/replay.txt" <<'EOF'
import hashlib, hmac, json, sys, time, urllib.request
port, secret, cs = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({"type": "checkout.session.completed",
                   "data": {"object": {"id": cs, "payment_status": "paid",
                    "metadata": {"student_id": "2", "unit_id": "3.2.1"}}}}).encode()
ts = str(int(time.time()))
sig = "t=%s,v1=%s" % (ts, hmac.new(secret.encode(), ("%s." % ts).encode() + body,
                                    hashlib.sha256).hexdigest())
req = urllib.request.Request("http://127.0.0.1:%s/webhook/stripe" % port, data=body,
                             headers={"Stripe-Signature": sig}, method="POST")
with urllib.request.urlopen(req, timeout=10) as r:
    print(r.status, r.read().decode())
EOF
    check "replay answered 200 newly_enrolled=false" \
        grep -q "200 .*\"newly_enrolled\": false" "$ROOT/replay.txt"
    check "still exactly one enrollment row" \
        test "$(psql_sql "SELECT count(*) FROM enrollments;")" = "1"
    check "still exactly one activation event" \
        test "$(psql_sql "SELECT count(*) FROM events WHERE type='enrollment.activated';")" = "1"

    echo
    echo "== proof 7: cancel path and /submit copy are honest =="
    check "cancel page: nothing was charged" html_has "$JAR_NEW" /checkout/cancel "nothing was charged"
    check "/submit documents accounts and payments" html_has - /submit "Accounts and payments"
    CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -b "$JAR_NEW" "$APP/submissions/999999")"
    check "unknown submission id still 404s for a signed-in user" test "$CODE" = "404"

    rm -f "$ROOT"/*.html "$ROOT"/*.txt 2>/dev/null || true
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
