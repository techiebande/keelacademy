#!/usr/bin/env bash
# push-demo-setup.sh — S1.9 Part B: stand up the push -> verdict pipeline
# against a scratch context under /tmp (never the project repo's git).
#
# Starts, with recorded PIDs: scratch postgres (schema 0001-0003 + the
# demo student and a live budget row), the intake webhook server, the LLM
# proxy pointed at the REAL OpenAI upstream (key env-only, sourced from
# ~/.keelacademy.env, never echoed), and the worker in loop mode. Creates
# the scratch bare remote keel-3.2.1-alice.git with the post-receive hook
# installed (checkout + HMAC-signed webhook + idempotent re-push), and a
# golden-derived student working repo ready to push.
#
# Setup PERSISTS (the human push happens after this returns); cleanup is
# only via push-demo-teardown.sh. Refuses to run twice.
#
# After setup, the single human act is:
#     cd /tmp/keel-push-demo/keel-3.2.1-alice && git push origin main
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../schema"
INTAKE="$SCRIPT_DIR/../intake/server.py"
PROXY="$SCRIPT_DIR/../proxy/server.py"
WORKER="$SCRIPT_DIR/../worker.py"
HOOK_TEMPLATE="$SCRIPT_DIR/push-demo-post-receive"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GOLDEN="$REPO_ROOT/content/golden/3.2.1/s01-textbook"
CORPUS="$REPO_ROOT/content/golden/3.2.1/s14-artifact-evidence/claims_messy.jsonl"

ROOT="/tmp/keel-push-demo"
REPO_NAME="keel-3.2.1-alice"
PUSHER_EMAIL="alice@keel.test"
IMAGE="postgres:16-alpine"
CONTAINER="keel-push-demo-pg"
DB_USER="smoke"
DB_NAME="grading"
DB_PORT=""
INTAKE_PORT=""
PROXY_PORT=""

if [ -e "$ROOT" ]; then
    echo "FAIL: $ROOT already exists — run push-demo-teardown.sh first (setup persists by design)" >&2
    exit 1
fi

# Prefer the Linux docker CLI; fall back to Docker Desktop's Windows binary
# when this WSL distro lacks /var/run/docker.sock.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
else
    echo "FAIL: no usable docker CLI found" >&2
    exit 1
fi

# Platform key: env-only. Sourced per the secrets convention, never echoed,
# never written anywhere under $ROOT.
if [ ! -f "$HOME/.keelacademy.env" ]; then
    echo "FAIL: ~/.keelacademy.env not found (needs OPENAI_API_KEY)" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1090
source "$HOME/.keelacademy.env"
set +a
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "FAIL: OPENAI_API_KEY not set after sourcing ~/.keelacademy.env" >&2
    exit 1
fi

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

mkdir -p "$ROOT"/{logs,submissions,remote,student}

echo "== starting $IMAGE as $CONTAINER =="
DB_PORT="$(free_port)"
"$DOCKER" run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$DB_USER" -e POSTGRES_PASSWORD=smoke -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:$DB_PORT:5432" "$IMAGE" >/dev/null

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

echo "== applying schema 0001 + 0002 + 0003 =="
for m in 0001_init 0002_intake 0003_budgets; do
    "$DOCKER" exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
        < "$SCHEMA_DIR/$m.sql" >/dev/null
done

echo "== seeding registered pusher $PUSHER_EMAIL with a live budget row =="
"$DOCKER" exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
INSERT INTO students (email, display_name) VALUES ('$PUSHER_EMAIL', 'Alice');
INSERT INTO budgets (student_id, tokens_cap, tokens_used)
SELECT id, 5000, 0 FROM students WHERE email = '$PUSHER_EMAIL';" >/dev/null

echo "== webhook secret =="
SECRET_FILE="$ROOT/webhook-secret"
umask 077
python3 -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_FILE"
umask 022
echo "written to $SECRET_FILE (chmod 600)"

echo "== starting intake + proxy (real upstream) + worker loop =="
INTAKE_PORT="$(free_port)"
PROXY_PORT="$(free_port)"
DB_CMD_PLAIN="$DOCKER exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"

KEEL_INTAKE_PORT="$INTAKE_PORT" \
KEEL_WEBHOOK_SECRET="$(cat "$SECRET_FILE")" \
KEEL_DB_CMD="$DB_CMD_PLAIN" \
    python3 "$INTAKE" >> "$ROOT/logs/intake.log" 2>&1 &
INTAKE_PID=$!

KEEL_PROXY_PORT="$PROXY_PORT" \
KEEL_PROXY_UPSTREAM_URL="https://api.openai.com/v1" \
KEEL_DB_CMD="$DB_CMD_PLAIN" \
    python3 "$PROXY" >> "$ROOT/logs/proxy.log" 2>&1 &
PROXY_PID=$!

KEEL_DB_CMD="$DB_CMD_PLAIN" \
KEEL_SUBMISSIONS_DIR="$ROOT/submissions" \
KEEL_PROXY_URL="http://127.0.0.1:$PROXY_PORT" \
KEEL_TRACE_LOG="$ROOT/logs/trace.jsonl" \
KEEL_SANDBOX_IMAGE="keel-runner:0.1" \
KEEL_POLL_INTERVAL_S="0.5" \
KEEL_GRADE_SLEEP_S="0.2" \
    python3 "$WORKER" >> "$ROOT/logs/worker.log" 2>&1 &
WORKER_PID=$!

printf 'INTAKE_PID=%s\nPROXY_PID=%s\nWORKER_PID=%s\nCONTAINER=%s\n' \
    "$INTAKE_PID" "$PROXY_PID" "$WORKER_PID" "$CONTAINER" > "$ROOT/pids.env"

wait_ready() {  # $1 = pid, $2 = port, $3 = name
    for i in $(seq 1 60); do
        if ! kill -0 "$1" 2>/dev/null; then
            echo "FAIL: $3 died at startup — $ROOT/logs has the output" >&2
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
wait_ready "$INTAKE_PID" "$INTAKE_PORT" "intake server"
wait_ready "$PROXY_PID" "$PROXY_PORT" "proxy"

echo "== creating bare remote $ROOT/remote/$REPO_NAME.git with the post-receive hook =="
BARE="$ROOT/remote/$REPO_NAME.git"
git init -q --bare -b main "$BARE"
# Allow the delete-then-re-push choreography used to re-deliver the same
# commit (idempotency proof); git denies deleting the current branch by
# default, which would block it before the hook ever runs.
git -C "$BARE" config receive.denyDeleteCurrent ignore
sed -e "s|@INTAKE_URL@|http://127.0.0.1:$INTAKE_PORT/webhook/github|" \
    -e "s|@SECRET_FILE@|$SECRET_FILE|" \
    -e "s|@SUBS_DIR@|$ROOT/submissions|" \
    -e "s|@PUSHER_MAP@|$ROOT/pusher-map|" \
    -e "s|@DB_CMD@|$DB_CMD_PLAIN|" \
    -e "s|@CLONE_URL@|$BARE|" \
    -e "s|@REPO_NAME@|$REPO_NAME|" \
    "$HOOK_TEMPLATE" > "$BARE/hooks/post-receive"
chmod +x "$BARE/hooks/post-receive"
printf '%s %s\n' "$REPO_NAME" "$PUSHER_EMAIL" > "$ROOT/pusher-map"

echo "== creating golden-derived student repo $ROOT/student/$REPO_NAME =="
STUDENT="$ROOT/student/$REPO_NAME"
git init -q -b main "$STUDENT"
# Golden-derived = the student's own files only; grade.yaml is calibration
# data and never ships in a submission repo.
cp "$GOLDEN/extract_claims.py" "$STUDENT/"
cp -r "$GOLDEN/tests" "$STUDENT/"
# The student's variant corpus (the layer-1 runner's data contract).
cp "$CORPUS" "$STUDENT/claims_messy.jsonl"
git -C "$STUDENT" add -A
git -C "$STUDENT" -c user.name="Alice" -c user.email="$PUSHER_EMAIL" \
    commit -q -m "unit 3.2.1 build submission"
git -C "$STUDENT" remote add origin "$BARE"

cat <<SUMMARY

== push -> verdict pipeline READY (persists until push-demo-teardown.sh) ==
   bare remote : $BARE
   student repo: $STUDENT  (branch main, one commit)
   pusher map  : $REPO_NAME -> $PUSHER_EMAIL (registered, budget cap 5000)
   intake      : http://127.0.0.1:$INTAKE_PORT/webhook/github  (pid $INTAKE_PID)
   proxy       : http://127.0.0.1:$PROXY_PORT  -> https://api.openai.com/v1  (pid $PROXY_PID)
   worker      : loop mode, submissions at $ROOT/submissions  (pid $WORKER_PID)
   pids/env    : $ROOT/pids.env

   THE ONLY HUMAN ACT:
       cd $STUDENT && git push origin main
   then watch a verdict appear with zero further input.
SUMMARY
