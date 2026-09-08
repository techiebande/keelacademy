#!/usr/bin/env python3
"""smoke-worker-checks.py — The four S1.3 proof checks for the queue worker (stdlib only).

Env (set by smoke-worker.sh):
  WORKER_DOCKER, WORKER_CONTAINER, WORKER_DB_USER, WORKER_DB_NAME,
  WORKER_DB_CMD, WORKER_SCRIPT

Checks:
  (a) happy path: worker one-shot -> exactly 1 verdict for submission 1,
      status 'graded', exactly 1 verdict.issued event naming it, overall
      matches sha-parity rule;
  (b) kill mid-grade: KEEL_GRADE_SLEEP_S=8, start worker in background,
      SIGKILL it after ~2s -> intermediate state status='grading', ZERO verdicts;
      restart worker one-shot -> exactly 1 verdict, status 'graded', exactly
      1 verdict.issued event (recovery path);
  (c) race: one new queued submission, TWO workers started simultaneously
      (sleep long enough to overlap) -> exactly 1 verdict total, loser exits 0;
  (d) poison redelivery: force already-verdicted submission 1 back to 'queued',
      run worker one-shot -> insert conflicts, status ends 'graded', verdict
      count STILL 1, no duplicate verdict.issued event.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time

DOCKER = os.environ["WORKER_DOCKER"]
CONTAINER = os.environ["WORKER_CONTAINER"]
DB_USER = os.environ["WORKER_DB_USER"]
DB_NAME = os.environ["WORKER_DB_NAME"]
DB_CMD = os.environ["WORKER_DB_CMD"]
WORKER_SCRIPT = os.environ["WORKER_SCRIPT"]

failures = []


def psql(sql: str) -> str:
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-tA", "-F", "\t", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )
    return out.stdout.decode("utf-8").strip()


def check(letter: str, desc: str, ok: bool, detail: str = ""):
    status_str = "PASS" if ok else "FAIL"
    print("%s %s: %s%s" % (status_str, letter, desc, (" — " + detail) if detail else ""))
    if not ok:
        failures.append(letter)


def run_worker_once(env_overrides=None):
    env = os.environ.copy()
    env["KEEL_DB_CMD"] = DB_CMD
    env["KEEL_WORKER_ONCE"] = "1"
    env["KEEL_GRADE_SLEEP_S"] = "0.1"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, WORKER_SCRIPT],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


# ==============================================================================
# Check (a) Happy path: worker one-shot -> exactly 1 verdict for submission 1
# ==============================================================================
sha_a = "a1" * 20
psql(
    "INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, pusher_email, status) "
    "VALUES (1, '3.2.1', '%s', 'https://github.com/keel-academy/keel-3.2.1-alice.git', 'alice@keel.test', 'queued');"
    % sha_a
)

# Deterministic expected overall from sha parity
h_a = hashlib.sha256(sha_a.encode("utf-8")).hexdigest()
expected_overall_a = "pass" if (int(h_a, 16) % 2 == 0) else "fail"

proc_a = run_worker_once()
sub_row_a = psql("SELECT id, status, unit_id, commit_sha FROM submissions WHERE id = 1;")
sub_id_a, sub_status_a, sub_unit_a, sub_sha_a = sub_row_a.split("\t")

verdict_row_a = psql("SELECT count(*), min(overall), min(rubric_id) FROM verdicts WHERE submission_id = 1;")
v_count_a, v_overall_a, v_rubric_a = verdict_row_a.split("\t")

event_row_a = psql(
    "SELECT count(*), min(payload->>'submission_id'), min(payload->>'overall') "
    "FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '1';"
)
ev_count_a, ev_sub_a, ev_overall_a = event_row_a.split("\t")

ok_a = (
    proc_a.returncode == 0
    and sub_status_a == "graded"
    and v_count_a == "1"
    and v_overall_a == expected_overall_a
    and ev_count_a == "1"
    and ev_sub_a == "1"
    and ev_overall_a == expected_overall_a
)
check(
    "a",
    "happy path -> 1 verdict for sub 1, status='graded', 1 verdict.issued event, sha-parity match",
    ok_a,
    "status=%s verdicts=%s overall=%s (expected=%s, sha256_even=%s) events=%s"
    % (sub_status_a, v_count_a, v_overall_a, expected_overall_a, expected_overall_a == "pass", ev_count_a),
)


# ==============================================================================
# Check (b) Kill mid-grade: SIGKILL after ~2s -> intermediate state, then restart recovery
# ==============================================================================
sha_b = "b2" * 20
psql(
    "INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, pusher_email, status) "
    "VALUES (1, '3.2.1', '%s', 'https://github.com/keel-academy/keel-3.2.1-alice.git', 'alice@keel.test', 'queued');"
    % sha_b
)

env_b = os.environ.copy()
env_b["KEEL_DB_CMD"] = DB_CMD
env_b["KEEL_WORKER_ONCE"] = "1"
env_b["KEEL_GRADE_SLEEP_S"] = "8"
worker_proc_b = subprocess.Popen(
    [sys.executable, WORKER_SCRIPT],
    env=env_b,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Allow worker to claim row and enter grade sleep
time.sleep(2.0)

# Send SIGKILL to terminate mid-grade
os.kill(worker_proc_b.pid, signal.SIGKILL)
worker_proc_b.wait()

# Inspect intermediate state
mid_status_b = psql("SELECT status FROM submissions WHERE id = 2;")
mid_v_count_b = psql("SELECT count(*) FROM verdicts WHERE submission_id = 2;")
mid_ev_count_b = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '2';")

print("  [intermediate state at SIGKILL: status=%s, verdicts=%s, events=%s]" % (mid_status_b, mid_v_count_b, mid_ev_count_b))

# Restart worker in one-shot mode with reaper threshold = 0s
proc_b_recover = run_worker_once({"KEEL_STALE_AFTER_S": "0", "KEEL_GRADE_SLEEP_S": "0.1"})

final_status_b = psql("SELECT status FROM submissions WHERE id = 2;")
final_v_count_b = psql("SELECT count(*) FROM verdicts WHERE submission_id = 2;")
final_ev_count_b = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '2';")

ok_b = (
    mid_status_b == "grading"
    and mid_v_count_b == "0"
    and proc_b_recover.returncode == 0
    and final_status_b == "graded"
    and final_v_count_b == "1"
    and final_ev_count_b == "1"
)
check(
    "b",
    "kill mid-grade -> intermediate stuck grading/0 verdicts, restart recovers -> 1 verdict, status='graded'",
    ok_b,
    "killed: status=%s verdicts=%s | recovered: status=%s verdicts=%s events=%s"
    % (mid_status_b, mid_v_count_b, final_status_b, final_v_count_b, final_ev_count_b),
)


# ==============================================================================
# Check (c) Race: one queued submission, TWO concurrent workers
# ==============================================================================
sha_c = "c3" * 20
psql(
    "INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, pusher_email, status) "
    "VALUES (1, '3.2.1', '%s', 'https://github.com/keel-academy/keel-3.2.1-alice.git', 'alice@keel.test', 'queued');"
    % sha_c
)

env_c = os.environ.copy()
env_c["KEEL_DB_CMD"] = DB_CMD
env_c["KEEL_WORKER_ONCE"] = "1"
env_c["KEEL_GRADE_SLEEP_S"] = "3"

w1 = subprocess.Popen([sys.executable, WORKER_SCRIPT], env=env_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
w2 = subprocess.Popen([sys.executable, WORKER_SCRIPT], env=env_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

w1_out, w1_err = w1.communicate()
w2_out, w2_err = w2.communicate()

sub_status_c = psql("SELECT status FROM submissions WHERE id = 3;")
v_count_c = psql("SELECT count(*) FROM verdicts WHERE submission_id = 3;")
ev_count_c = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '3';")

ok_c = (
    w1.returncode == 0
    and w2.returncode == 0
    and sub_status_c == "graded"
    and v_count_c == "1"
    and ev_count_c == "1"
)
check(
    "c",
    "race -> two concurrent workers on 1 submission -> exactly 1 verdict total, loser exits 0 without error noise",
    ok_c,
    "worker1_exit=%d worker2_exit=%d status=%s verdicts=%s events=%s"
    % (w1.returncode, w2.returncode, sub_status_c, v_count_c, ev_count_c),
)


# ==============================================================================
# Check (d) Poison redelivery: force already-verdicted submission 1 back to 'queued'
# ==============================================================================
psql("UPDATE submissions SET status = 'queued' WHERE id = 1;")
v_before_d = psql("SELECT count(*) FROM verdicts WHERE submission_id = 1;")
ev_before_d = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '1';")

proc_d = run_worker_once({"KEEL_GRADE_SLEEP_S": "0.1"})

sub_status_d = psql("SELECT status FROM submissions WHERE id = 1;")
v_after_d = psql("SELECT count(*) FROM verdicts WHERE submission_id = 1;")
ev_after_d = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = '1';")
total_verdicts = psql("SELECT count(*) FROM verdicts;")
total_events = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued';")

ok_d = (
    proc_d.returncode == 0
    and v_before_d == "1"
    and ev_before_d == "1"
    and sub_status_d == "graded"
    and v_after_d == "1"
    and ev_after_d == "1"
    and total_verdicts == "3"
    and total_events == "3"
)
check(
    "d",
    "poison redelivery -> insert conflicts, status ends 'graded', verdict count STILL 1, no duplicate event",
    ok_d,
    "status=%s sub1_verdicts=%s sub1_events=%s total_verdicts=%s total_verdict_events=%s"
    % (sub_status_d, v_after_d, ev_after_d, total_verdicts, total_events),
)


if failures:
    print("\nFAILED: %s" % ", ".join(failures))
    sys.exit(1)
