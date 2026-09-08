#!/usr/bin/env bash
# NOTE: the copy greps below assert the copy the pages render today. A session
# that rewrites that copy updates these greps to the new strings and re-runs
# this demo green (the 2026-08-27 copy-unfreeze decision in build-state.md).
# verdict-demo.sh — S2.4 end-to-end proof: a real git push becomes real rows
# and the learner app's verdict page renders them read-only.
#
# A verdict page opens only for the account that pushed the commit, so this
# demo also stands up the S2.5 enrollment service and runs the app in its
# offline auth mode: the proof signs alice and bob in through the app's own
# sign-up form and reads every page with that account's cookie, exactly as a
# student's browser would.
#
# Modes:
#   setup     Stand up the S1.9 push -> verdict pipeline (push-demo-setup.sh,
#             run under setsid so the daemons survive), then add: the S2.4
#             read-only reader, the enrollment service that links a signed-in
#             account to its grading row, the learner app dev server (setsid),
#             a second repo for a budget-blocked student (bob), and a raised
#             budget for alice so multiple proof pushes fit. Persists until
#             teardown.
#   prove     Run setup if needed, then perform the worker-side proof: graded,
#             grading (mid-flight, worker SIGSTOP'd for a stable window),
#             queued (worker frozen across the push), error (bob's exhausted
#             budget), /submit, and an unknown id's honest 404. Exit 0 only if
#             every assertion holds.
#   teardown  Stop the reader, enroll and app daemons, then run
#             push-demo-teardown.sh (which removes the containers and
#             /tmp/keel-push-demo).
#
# No secret is ever echoed or written under $ROOT; the platform key stays in
# the setup script's process environment (sourced from ~/.keelacademy.env).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_DIR="$REPO_ROOT/platform/app"
READER="$SCRIPT_DIR/../reader/server.py"
ENROLL="$SCRIPT_DIR/../enroll/server.py"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
PUSH_SETUP="$SCRIPT_DIR/push-demo-setup.sh"
PUSH_TEARDOWN="$SCRIPT_DIR/push-demo-teardown.sh"
HOOK_TEMPLATE="$SCRIPT_DIR/push-demo-post-receive"

ROOT="/tmp/keel-push-demo"
ALICE_REPO="keel-3.2.1-alice"
BOB_REPO="keel-3.2.1-bob"
PUSHER_EMAIL="alice@keel.test"
BOB_EMAIL="bob@keel.test"
CONTAINER="keel-push-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
GOLDEN="$REPO_ROOT/content/golden/3.2.1/s01-textbook"
CORPUS="$REPO_ROOT/content/golden/3.2.1/s14-artifact-evidence/claims_messy.jsonl"
SETUP_LOG="/tmp/keel-verdict-setup.log"

# Test-mode placeholders for the two shared secrets this demo needs. Neither
# is a credential: the app token guards a loopback-only service, and the auth
# secret signs cookies for the offline auth fake. No real key is used here.
APP_TOKEN="verdict-demo-app-token"
AUTH_SECRET="verdict-demo-offline-auth-secret"

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

psql_sql() {  # psql_sql <sql> — one -tA session
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -tA <<< "$1"
}

wait_http() {  # wait_http <url> <name> [timeout_s]
    local timeout="${3:-90}" i
    for i in $(seq 1 "$((timeout * 2))"); do
        if curl -sf -o /dev/null --max-time 10 "$1"; then return 0; fi
        sleep 0.5
    done
    echo "FAIL: $2 never became ready at $1" >&2
    return 1
}

wait_status() {  # wait_status <submission_id> <status> [timeout_s]
    local id="$1" want="$2" timeout="${3:-180}" i got=""
    for i in $(seq 1 "$((timeout * 4))"); do
        got="$(curl -sf --max-time 5 "http://127.0.0.1:${READER_PORT:-}/submissions/$id" 2>/dev/null \
            | python3 -c 'import json,sys; print(json.load(sys.stdin)["submission"]["status"])' 2>/dev/null || true)"
        if [ "$got" = "$want" ]; then return 0; fi
        sleep 0.25
    done
    echo "FAIL: submission $id never reached status '$want' (last: '${got:-none}')" >&2
    return 1
}

do_setup() {
    if [ ! -f "$ROOT/pids.env" ]; then
        echo "== starting the S1.9 push -> verdict pipeline (setsid) =="
        setsid bash "$PUSH_SETUP" > "$SETUP_LOG" 2>&1 &
        for i in $(seq 1 180); do
            [ -f "$ROOT/pids.env" ] && [ -d "$ROOT/student/$ALICE_REPO" ] && break
            sleep 1
        done
        if [ ! -f "$ROOT/pids.env" ]; then
            echo "FAIL: push-demo-setup did not finish — see $SETUP_LOG" >&2
            exit 1
        fi
        echo "   pipeline up (summary in $SETUP_LOG)"
    fi
    # shellcheck disable=SC1090
    . "$ROOT/pids.env"

    if [ -n "${READER_PID:-}" ] && kill -0 "$READER_PID" 2>/dev/null \
        && [ -n "${ENROLL_PID:-}" ] && kill -0 "$ENROLL_PID" 2>/dev/null; then
        echo "== demo already set up (reader pid $READER_PID, app port ${APP_PORT:-?}) =="
        return 0
    fi

    # The verdict page resolves ownership through the enrollment service, so
    # this demo needs the tables that service owns. push-demo-setup applies
    # 0001..0003; add 0004 and 0005 once, guarded so a re-stand does not
    # re-run a migration that is not written to be re-runnable.
    if [ "$(psql_sql "SELECT to_regclass('public.enrollments') IS NULL;")" = "t" ]; then
        echo "== applying schema 0004 + 0005 (enrollment tables) =="
        for m in 0004_enrollments 0005_rebates; do
            "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
                -v ON_ERROR_STOP=1 < "$SCHEMA_DIR/$m.sql" >/dev/null
        done
    fi

    echo "== raising alice's budget (multiple proof pushes) =="
    psql_sql "UPDATE budgets SET tokens_cap = 100000
              WHERE student_id = (SELECT id FROM students WHERE email = '$PUSHER_EMAIL');"

    echo "== seeding bob (budget already exhausted: the real error path) =="
    psql_sql "INSERT INTO students (email, display_name) VALUES ('$BOB_EMAIL', 'Bob')
              ON CONFLICT (email) DO NOTHING;
              INSERT INTO budgets (student_id, tokens_cap, tokens_used)
              SELECT id, 100, 100 FROM students WHERE email = '$BOB_EMAIL'
              ON CONFLICT (student_id) DO NOTHING;
              UPDATE budgets SET tokens_cap = 100, tokens_used = 100
              WHERE student_id = (SELECT id FROM students WHERE email = '$BOB_EMAIL');"
    grep -q "^$BOB_REPO " "$ROOT/pusher-map" || printf '%s %s\n' "$BOB_REPO" "$BOB_EMAIL" >> "$ROOT/pusher-map"

    echo "== creating bob's bare remote + hook (same intake, same secret) =="
    BARE_ALICE="$ROOT/remote/$ALICE_REPO.git"
    BARE_BOB="$ROOT/remote/$BOB_REPO.git"
    INTAKE_URL="$(grep -m1 '^INTAKE_URL=' "$BARE_ALICE/hooks/post-receive" | cut -d'"' -f2)"
    SECRET_FILE="$(grep -m1 '^SECRET_FILE=' "$BARE_ALICE/hooks/post-receive" | cut -d'"' -f2)"
    SUBS_DIR="$(grep -m1 '^SUBS_DIR=' "$BARE_ALICE/hooks/post-receive" | cut -d'"' -f2)"
    if [ ! -d "$BARE_BOB" ]; then
        git init -q --bare -b main "$BARE_BOB"
        git -C "$BARE_BOB" config receive.denyDeleteCurrent ignore
        sed -e "s|@INTAKE_URL@|$INTAKE_URL|" \
            -e "s|@SECRET_FILE@|$SECRET_FILE|" \
            -e "s|@SUBS_DIR@|$SUBS_DIR|" \
            -e "s|@PUSHER_MAP@|$ROOT/pusher-map|" \
            -e "s|@DB_CMD@|$DB_CMD_PLAIN|" \
            -e "s|@CLONE_URL@|$BARE_BOB|" \
            -e "s|@REPO_NAME@|$BOB_REPO|" \
            "$HOOK_TEMPLATE" > "$BARE_BOB/hooks/post-receive"
        chmod +x "$BARE_BOB/hooks/post-receive"
    fi

    echo "== creating bob's student repo =="
    BOB_STUDENT="$ROOT/student/$BOB_REPO"
    if [ ! -d "$BOB_STUDENT/.git" ]; then
        git init -q -b main "$BOB_STUDENT"
        cp "$GOLDEN/extract_claims.py" "$BOB_STUDENT/"
        cp -r "$GOLDEN/tests" "$BOB_STUDENT/"
        cp "$CORPUS" "$BOB_STUDENT/claims_messy.jsonl"
        git -C "$BOB_STUDENT" add -A
        git -C "$BOB_STUDENT" -c user.name="Bob" -c user.email="$BOB_EMAIL" \
            commit -q -m "unit 3.2.1 build submission"
        git -C "$BOB_STUDENT" remote add origin "$BARE_BOB"
    fi

    echo "== starting the read-only reader (setsid) =="
    READER_PORT="$(free_port)"
    KEEL_READER_PORT="$READER_PORT" KEEL_DB_CMD="$DB_CMD_PLAIN" \
        setsid python3 "$READER" >> "$ROOT/logs/reader.log" 2>&1 < /dev/null &
    READER_PID=$!
    wait_http "http://127.0.0.1:$READER_PORT/healthz" "reader" \
        || { kill "$READER_PID" 2>/dev/null || true; exit 1; }

    echo "== starting the enrollment service (setsid) =="
    ENROLL_PORT="$(free_port)"
    ( exec env KEEL_ENROLL_PORT="$ENROLL_PORT" \
        KEEL_DB_CMD="$DB_CMD_PLAIN" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_DEFAULT_BUDGET_TOKENS="5000" \
        setsid python3 "$ENROLL" ) >> "$ROOT/logs/enroll.log" 2>&1 < /dev/null &
    ENROLL_PID=$!
    wait_http "http://127.0.0.1:$ENROLL_PORT/healthz" "enroll service" \
        || { kill "$READER_PID" "$ENROLL_PID" 2>/dev/null || true; exit 1; }

    echo "== starting the learner app dev server (setsid) =="
    if pgrep -f "node_modules/.bin/next dev" >/dev/null 2>&1; then
        echo "FAIL: a next dev server is already running for this app (Next refuses a second one). Kill it first:" >&2
        pgrep -af "node_modules/.bin/next dev" >&2 || true
        exit 1
    fi
    APP_PORT="$(free_port)"
    # exec inside the subshell so $! is the setsid'd session leader itself,
    # and the process-group kill in teardown reaches next's render workers.
    ( cd "$APP_DIR" && exec env KEEL_READER_URL="http://127.0.0.1:$READER_PORT" \
        KEEL_ENROLL_URL="http://127.0.0.1:$ENROLL_PORT" \
        KEEL_ENROLL_SECRET="$APP_TOKEN" \
        KEEL_OFFLINE_AUTH_SECRET="$AUTH_SECRET" \
        KEEL_OFFLINE_AUTH_STORE="$ROOT/offline-auth-store.json" \
        setsid ./node_modules/.bin/next dev -p "$APP_PORT" -H 127.0.0.1 ) \
        >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
    APP_PID=$!
    if ! wait_http "http://127.0.0.1:$APP_PORT/" "learner app"; then
        for pid in "$READER_PID" "$ENROLL_PID" "$APP_PID"; do
            kill -TERM -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        done
        exit 1
    fi

    # Persist the S2.4 additions where teardown (and re-runs) can find them.
    printf 'READER_PID=%s\nREADER_PORT=%s\nENROLL_PID=%s\nENROLL_PORT=%s\nAPP_PID=%s\nAPP_PORT=%s\n' \
        "$READER_PID" "$READER_PORT" "$ENROLL_PID" "$ENROLL_PORT" "$APP_PID" "$APP_PORT" \
        >> "$ROOT/pids.env"

    cat <<SUMMARY

== verdict-page demo READY (persists until teardown) ==
   app        : http://127.0.0.1:$APP_PORT/submit
   reader     : http://127.0.0.1:$READER_PORT/healthz  (pid $READER_PID)
   enroll svc : http://127.0.0.1:$ENROLL_PORT/healthz  (pid $ENROLL_PID)
   alice repo : $ROOT/student/$ALICE_REPO  (registered, budget raised)
   bob repo   : $BOB_STUDENT  (registered, budget exhausted -> error path)
   logs       : $ROOT/logs/{reader,enroll,app}.log

   YOUR PUSH (creates the submission the verdict page renders):
       cd $ROOT/student/$ALICE_REPO && git push origin main
   then sign in as $PUSHER_EMAIL at http://127.0.0.1:$APP_PORT/sign-up
   and open http://127.0.0.1:$APP_PORT/submissions/<id-from-the-hook-response>
   (a verdict page opens only for the account that pushed the commit)

   teardown: bash $SCRIPT_DIR/verdict-demo.sh teardown
SUMMARY
}

PASS_COUNT=0
FAIL_COUNT=0
check() {  # check <name> <cmd...> — run in a subshell; PASS/FAIL tally
    local name="$1"; shift
    if ( "$@" ) >/dev/null 2>&1; then
        echo "PASS: $name"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "FAIL: $name"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

html_has() {  # html_has <cookie-jar-or-"-"> <path> <needle>
    # The needle is matched with a bash pattern rather than a pipe into
    # `grep -q`, deliberately. grep exits on its first match, so with a page
    # larger than the 64KB pipe buffer the writer is still writing when the
    # pipe closes, dies of SIGPIPE, and `set -o pipefail` reports a found
    # needle as a failed assertion. The earlier the needle sits in the page,
    # the more often that happens.
    #
    # Three attempts, because this page is rendered from two live services on
    # every request: one momentary failure there renders the honest "we could
    # not confirm this is yours" fallback, which is correct behaviour and not
    # what these assertions are about.
    local jar="$1" path="$2" needle="$3" body attempt
    for attempt in 1 2 3; do
        if [ "$jar" = "-" ]; then
            body="$(curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT$path")" || body=""
        else
            body="$(curl -sf --max-time 30 -b "$jar" "http://127.0.0.1:$APP_PORT$path")" || body=""
        fi
        case "$body" in *"$needle"*) return 0 ;; esac
        sleep 1
    done
    # Keep the page that did not carry the needle: a copy-grep failure and a
    # render failure look identical in the PASS/FAIL tally otherwise.
    printf '%s' "$body" > "$ROOT/logs/miss-$(printf '%s' "$path$needle" | tr -c 'a-zA-Z0-9' '-' | cut -c1-60).html"
    return 1
}

status_of() {  # status_of <cookie-jar-or-"-"> <path> — HTTP code only
    local jar="$1"
    if [ "$jar" = "-" ]; then
        curl -s -o /dev/null -w "%{http_code}" --max-time 30 "http://127.0.0.1:$APP_PORT$2"
    else
        curl -s -o /dev/null -w "%{http_code}" --max-time 30 -b "$jar" \
            "http://127.0.0.1:$APP_PORT$2"
    fi
}

# Extract the progressive-enhancement action id from a rendered form: Next
# injects <input type="hidden" name="$ACTION_ID_..."> for no-JS posts.
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

sign_in_as() {  # sign_in_as <jar> <name> <email> — drive the app's own forms
    # Prefer sign-in: a second prove run against a live demo finds the account
    # already created, and the offline auth fake answers a repeat sign-up with
    # "that email already has an account". Sign-up is the first-run path.
    local jar="$1" who="$2" email="$3"
    rm -f "$jar"
    if post_auth_form "$jar" /sign-in "email=$email" "next=/me"; then return 0; fi
    post_auth_form "$jar" /sign-up "name=$who" "email=$email" "next=/me"
}

post_auth_form() {  # post_auth_form <jar> <path> <field=value>...
    local jar="$1" path="$2"; shift 2
    local form="$ROOT/auth-form.html" action code args=() kv
    curl -sf --max-time 30 "http://127.0.0.1:$APP_PORT$path" -o "$form" || return 1
    action="$(action_id "$form")" || return 1
    args=(-F "$action=")
    for kv in "$@"; do args+=(-F "$kv"); done
    # The rendered forms carry encType="multipart/form-data", so the no-JS
    # posts mirror that exactly with curl -F.
    code="$(curl -s --max-time 30 -o /dev/null -w "%{http_code}" -b "$jar" -c "$jar" \
        -X POST "http://127.0.0.1:$APP_PORT$path" "${args[@]}")"
    [ "$code" = "303" ] || return 1
    grep -q "keel_session" "$jar"
}

json_is() {  # json_is <submission_id> <python-expr over doc>
    local id="$1" expr="$2"
    curl -sf --max-time 10 "http://127.0.0.1:$READER_PORT/submissions/$id" \
        | python3 -c "import json,sys; doc=json.load(sys.stdin); sys.exit(0 if ($expr) else 1)"
}

new_commit_in() {  # push N creates a fresh commit so each push is a new submission
    local repo="$1" n="$2"
    echo "proof push $n" >> "$repo/NOTES.md"
    git -C "$repo" add -A
    git -C "$repo" -c user.name="Alice" -c user.email="$PUSHER_EMAIL" \
        commit -q -m "proof push $n"
}

do_prove() {
    do_setup  # idempotent: brings up whatever is not already running
    # shellcheck disable=SC1090
    . "$ROOT/pids.env"
    ALICE="$ROOT/student/$ALICE_REPO"
    BOB="$ROOT/student/$BOB_REPO"
    JAR_ALICE="$ROOT/jar-alice.txt"
    JAR_BOB="$ROOT/jar-bob.txt"

    echo
    echo "== proof 0: the accounts sign in through the app's own form =="
    # Both students already have a grading row from pushing; signing up with
    # the same email claims that row, which is what makes their verdict pages
    # theirs. Every page assertion below is read with that account's cookie.
    check "alice signs in and claims her grading row" \
        sign_in_as "$JAR_ALICE" "Alice" "$PUSHER_EMAIL"
    check "bob signs in and claims his grading row" \
        sign_in_as "$JAR_BOB" "Bob" "$BOB_EMAIL"

    echo
    echo "== proof 1: a real push grades and the verdict page renders it =="
    new_commit_in "$ALICE" 1
    git -C "$ALICE" push -q origin main 2>&1 | sed 's/^/   /' || true
    ID_A="$(psql_sql "SELECT max(id) FROM submissions WHERE student_id = (SELECT id FROM students WHERE email = '$PUSHER_EMAIL');")"
    wait_status "$ID_A" graded
    echo "   submission $ID_A graded"
    check "reader: 8 layer-1 checks, all pass" \
        json_is "$ID_A" 'len(doc["verdict"]["json"]["layer1"]["checks"]) == 8 and all(c["status"] == "pass" for c in doc["verdict"]["json"]["layer1"]["checks"])'
    check "reader: judge criteria carry evidence" \
        json_is "$ID_A" 'len(doc["verdict"]["json"]["judge"]["criteria"]) == 5 and all(c["evidence"] for c in doc["verdict"]["json"]["judge"]["criteria"])'
    check "reader: rubric id + version + trace records" \
        json_is "$ID_A" 'doc["verdict"]["rubric_id"] == "rubric-3.2.1" and doc["verdict"]["rubric_version"] == 1 and len(doc["verdict"]["json"]["trace"]["records"]) > 0'
    check "reader: event timeline is created + issued" \
        json_is "$ID_A" '[e["type"] for e in doc["events"]] == ["submission.created", "verdict.issued"]'
    check "page: graded banner (Passed)" html_has "$JAR_ALICE" "/submissions/$ID_A" 'data-keel-status="graded"'
    check "page: layer-1 summary renders" html_has "$JAR_ALICE" "/submissions/$ID_A" "checks passed"
    check "page: judge section renders" html_has "$JAR_ALICE" "/submissions/$ID_A" "criteria passed"
    check "page: rubric identity renders" html_has "$JAR_ALICE" "/submissions/$ID_A" "rubric-3.2.1"
    check "page: budget charged renders" html_has "$JAR_ALICE" "/submissions/$ID_A" "tokens"
    check "page: timeline labels render" html_has "$JAR_ALICE" "/submissions/$ID_A" "Verdict issued"
    check "page: privacy note present" html_has "$JAR_ALICE" "/submissions/$ID_A" "This link is private"
    check "page: signed-out visitors are sent to sign-in" \
        test "$(status_of - "/submissions/$ID_A")" = "307"
    check "page: another account gets a 404, not a peek" \
        test "$(status_of "$JAR_BOB" "/submissions/$ID_A")" = "404"

    echo
    echo "== proof 2: mid-flight (grading) renders while the worker is paused =="
    new_commit_in "$ALICE" 2
    git -C "$ALICE" push -q origin main || true
    ID_B="$(psql_sql "SELECT max(id) FROM submissions;")"
    wait_status "$ID_B" grading
    kill -STOP "$WORKER_PID"
    echo "   submission $ID_B grading; worker $WORKER_PID frozen for a stable window"
    check "page: grading banner (live state)" html_has "$JAR_ALICE" "/submissions/$ID_B" 'data-keel-status="grading"'
    check "page: while-you-wait copy, no verdict sections" html_has "$JAR_ALICE" "/submissions/$ID_B" "While you wait"
    kill -CONT "$WORKER_PID"
    wait_status "$ID_B" graded
    echo "   submission $ID_B graded after resume"

    echo
    echo "== proof 3: queued renders when the worker cannot claim =="
    kill -STOP "$WORKER_PID"
    new_commit_in "$ALICE" 3
    git -C "$ALICE" push -q origin main || true
    ID_C="$(psql_sql "SELECT max(id) FROM submissions;")"
    sleep 2
    check "page: queued banner" html_has "$JAR_ALICE" "/submissions/$ID_C" 'data-keel-status="queued"'
    check "reader: row really is queued" json_is "$ID_C" 'doc["submission"]["status"] == "queued"'
    kill -CONT "$WORKER_PID"
    wait_status "$ID_C" graded
    echo "   submission $ID_C graded after resume"

    echo
    echo "== proof 4: the real error path (bob's exhausted budget) =="
    git -C "$BOB" push -q origin main || true
    ID_D="$(psql_sql "SELECT max(id) FROM submissions WHERE student_id = (SELECT id FROM students WHERE email = '$BOB_EMAIL');")"
    wait_status "$ID_D" error 240
    echo "   submission $ID_D errored (budget blocked)"
    check "reader: no verdict row, budget_blocked event" \
        json_is "$ID_D" 'doc["verdict"] is None and [e["type"] for e in doc["events"]] == ["submission.created", "grade.budget_blocked"]'
    check "page: error banner" html_has "$JAR_BOB" "/submissions/$ID_D" 'data-keel-status="error"'
    check "page: error explanation, not a verdict" html_has "$JAR_BOB" "/submissions/$ID_D" "What an error means"
    check "page: budget-blocked timeline label" html_has "$JAR_BOB" "/submissions/$ID_D" "Budget blocked"

    echo
    echo "== proof 5: /submit documents the flow; unknown ids 404 honestly =="
    check "page: /submit renders the push contract" html_has - "/submit" "What happens after the push"
    check "page: /submit names the repo pattern" html_has - "/submit" "your-suffix"
    check "page: /submit is honest about S2.5" html_has - "/submit" "What is not here yet"
    check "page: unknown submission id is a 404" \
        test "$(status_of "$JAR_ALICE" /submissions/999999)" = "404"
    check "page: malformed submission id is a 404" \
        test "$(status_of "$JAR_ALICE" /submissions/not-an-id)" = "404"
    CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://127.0.0.1:$READER_PORT/submissions/999999")"
    check "reader: unknown id 404 at the service too" test "$CODE" = "404"

    echo
    echo "== proof summary: $PASS_COUNT passed, $FAIL_COUNT failed =="
    [ "$FAIL_COUNT" -eq 0 ] || exit 1
}

do_teardown() {
    if [ -f "$ROOT/pids.env" ]; then
        # shellcheck disable=SC1090
        . "$ROOT/pids.env"
        for pid in ${APP_PID:-} ${READER_PID:-} ${ENROLL_PID:-}; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill -TERM -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
            fi
        done
    fi
    sleep 1
    if pgrep -f "reader/server.py" >/dev/null 2>&1 \
        || pgrep -f "enroll/server.py" >/dev/null 2>&1 \
        || pgrep -f "next dev -p ${APP_PORT:-} " >/dev/null 2>&1; then
        echo "FAIL: reader/enroll/app daemons survived the kill" >&2
        pgrep -af "reader/server.py|enroll/server.py|next dev -p" >&2 || true
        exit 1
    fi
    rm -f "$SETUP_LOG" "$ROOT/app.pid"
    bash "$PUSH_TEARDOWN"
}

case "${1:-}" in
    setup) do_setup ;;
    prove) do_prove ;;
    teardown) do_teardown ;;
    *) echo "usage: $0 {setup|prove|teardown}" >&2; exit 2 ;;
esac
