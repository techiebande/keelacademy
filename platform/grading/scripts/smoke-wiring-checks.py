#!/usr/bin/env python3
"""smoke-wiring-checks.py — the four S1.8 wiring proof checks (stdlib only).

Env (set by smoke-wiring.sh): WIRING_DOCKER, WIRING_CONTAINER, WIRING_DB_USER,
WIRING_DB_NAME, WIRING_DB_CMD, WIRING_WORKER, WIRING_SUBS_DIR,
WIRING_TRACE_LOG, WIRING_PROXY_PORT, WIRING_FAKE_PORT, WIRING_SERVER_LOG,
WIRING_REPO_ROOT (+ the worker-facing KEEL_* env the harness exported).

Checks:
  (a) real verdict: golden submission -> VERDICT row with rubric v1, real
      Layer-1 results (8 pass / 0 fail — the S1.9 fix gave the golden
      extractors the checks file's --data/--out/--log CLI and fixed the
      conservation check's premature $() expansion), full judge verdict via
      the proxy, trace records tagged caller=worker, alice's budget charged
      exactly the fake call's usage;
  (b) kill-mid-judge: SIGKILL the worker while the judge call is in flight
      (fake upstream holds it) -> status='grading', 0 verdicts; restart ->
      recovery resolves to EXACTLY one verdict, status='graded';
  (c) budget cutoff: exhausted student -> proxy 429 -> worker records
      status='error' + grade.budget_blocked event, NO verdict row, loop
      exits 0, upstream never forwarded;
  (d) rubric-version flow: temp v2 rubric -> fresh grade resolves v2 (zero
      code edits); v2 deleted -> next fresh grade resolves v1 again.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DOCKER = os.environ["WIRING_DOCKER"]
CONTAINER = os.environ["WIRING_CONTAINER"]
DB_USER = os.environ["WIRING_DB_USER"]
DB_NAME = os.environ["WIRING_DB_NAME"]
DB_CMD = os.environ["WIRING_DB_CMD"]
WORKER_SCRIPT = os.environ["WIRING_WORKER"]
SUBS_DIR = Path(os.environ["WIRING_SUBS_DIR"])
TRACE_LOG = Path(os.environ["WIRING_TRACE_LOG"])
SERVER_LOG = Path(os.environ["WIRING_SERVER_LOG"])
REPO_ROOT = Path(os.environ["WIRING_REPO_ROOT"])
GOLDEN = REPO_ROOT / "content" / "golden" / "3.2.1" / "s01-textbook"
CORPUS = REPO_ROOT / "content" / "golden" / "3.2.1" / "s14-artifact-evidence" / "claims_messy.jsonl"
RUBRIC_V2 = REPO_ROOT / "content" / "rubrics" / "3.2.1" / "v2.yaml"

failures = []


def psql(sql: str) -> str:
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-q", "-tA", "-F", "\t", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return out.stdout.decode("utf-8").strip()


def check(letter: str, desc: str, ok: bool, detail: str = ""):
    print("%s %s: %s%s" % ("PASS" if ok else "FAIL", letter, desc,
                           (" — " + detail) if detail else ""))
    if not ok:
        failures.append(letter)


def seed_submission(email: str, sha: str) -> int:
    """Intake-shaped seed: one queued submission + its files on disk (the
    s01-textbook golden plus the variant corpus the layer-1 runner expects)."""
    sub_id = int(psql(
        "INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, pusher_email, status) "
        "SELECT id, '3.2.1', '%s', 'https://github.com/keel-academy/keel-3.2.1.git', '%s', 'queued' "
        "FROM students WHERE email = '%s' RETURNING id;" % (sha, email, email)))
    sub_dir = SUBS_DIR / str(sub_id)
    shutil.copytree(GOLDEN, sub_dir)
    shutil.copy(CORPUS, sub_dir / "claims_messy.jsonl")
    return sub_id


def run_worker_once(env_overrides=None):
    env = os.environ.copy()
    env["KEEL_DB_CMD"] = DB_CMD
    env["KEEL_WORKER_ONCE"] = "1"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, WORKER_SCRIPT], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def fake_count() -> int:
    import urllib.request
    with urllib.request.urlopen(
        "http://127.0.0.1:%s/__count" % os.environ["WIRING_FAKE_PORT"], timeout=5
    ) as resp:
        return int(resp.read())


def trace_lines():
    try:
        return [json.loads(l) for l in TRACE_LOG.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


# ==============================================================================
# Check (a) Real verdict: rubric v1 + layer results + judge verdict + tagged trace
# ==============================================================================
sub_a = seed_submission("alice@keel.test", "a1" * 20)
count_before_a = fake_count()
proc_a = run_worker_once()

row_a = psql(
    "SELECT s.status, v.rubric_id, v.rubric_version, v.overall, v.verdict_json "
    "FROM submissions s JOIN verdicts v ON v.submission_id = s.id WHERE s.id = %d;" % sub_a)
if not row_a:
    print("  [debug] worker exit=%d\nstdout: %s\nstderr: %s\nsub status: %r"
          % (proc_a.returncode, proc_a.stdout.decode(errors="replace")[-800:],
             proc_a.stderr.decode(errors="replace")[-2000:],
             psql("SELECT status FROM submissions WHERE id = %d;" % sub_a)), file=sys.stderr)
status_a, rubric_a, version_a, overall_a, vjson_a = row_a.split("\t", 4)
vj_a = json.loads(vjson_a)
l1_pass = sorted(c["id"] for c in vj_a["layer1"]["checks"] if c["status"] == "pass")
l1_fail = sorted(c["id"] for c in vj_a["layer1"]["checks"] if c["status"] != "pass")
judge_ids = sorted(c["id"] for c in vj_a["judge"]["criteria"])
trace_recs = vj_a.get("trace", {}).get("records", [])
log_tagged = [r for r in trace_lines()
              if r.get("caller") == "worker" and r.get("call_id") == vj_a["trace"]["call_id"]]
used_a = int(psql("SELECT b.tokens_used FROM budgets b JOIN students s ON s.id = b.student_id "
                  "WHERE s.email = 'alice@keel.test';"))
ev_a = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' "
            "AND payload->>'submission_id' = '%d';" % sub_a)

ok_a = (
    proc_a.returncode == 0
    and status_a == "graded"
    and rubric_a == "rubric-3.2.1"
    and version_a == "1"
    and overall_a == "pass"
    and len(vj_a["layer1"]["checks"]) == 8
    and l1_pass == sorted([
        "schema-object-importable", "twenty-in-twenty-out",
        "outputs-are-valid-schema-objects", "fallback-never-raises-never-drops",
        "failures-logged", "end-to-end-run-conserves-records",
        "end-to-end-run-logs-fallbacks", "logged-failures-name-the-claim"])
    and len(l1_fail) == 0
    and judge_ids == sorted([
        "schema-constrained-generation", "pydantic-validation-boundary",
        "defined-fallback", "failures-logged", "conservation-tested"])
    and len(trace_recs) >= 1 and trace_recs[0].get("caller") == "worker"
    and len(log_tagged) == len(trace_recs)
    and used_a == 300  # one fake call: 50 prompt + 250 completion
    and fake_count() == count_before_a + 1
    and ev_a == "1"
)
check("a", "real verdict: rubric v1, 8 layer-1 results (8 pass/0 fail), judge verdict via proxy, "
           "worker-tagged trace, budget charged", ok_a,
      "status=%s rubric=%s v%s overall=%s l1=%dp/%df judge=%d criteria trace=%d/%d used=%d"
      % (status_a, rubric_a, version_a, overall_a, len(l1_pass), len(l1_fail),
         len(judge_ids), len(trace_recs), len(log_tagged), used_a))


# ==============================================================================
# Check (b) Kill mid-judge -> stuck grading/0 verdicts -> restart -> exactly one
# ==============================================================================
sub_b = seed_submission("alice@keel.test", "b2" * 20)
proxy_posts_before = SERVER_LOG.read_text().count("/v1/chat/completions")

env_b = os.environ.copy()
env_b["KEEL_DB_CMD"] = DB_CMD
env_b["KEEL_WORKER_ONCE"] = "1"
worker_b = subprocess.Popen([sys.executable, WORKER_SCRIPT], env=env_b,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# The fake upstream holds each judge call in flight (KEEL_FAKE_DELAY_S), so we
# can wait until THIS grading's proxy call has actually started, then kill.
deadline = time.time() + 180
while time.time() < deadline:
    if SERVER_LOG.read_text().count("/v1/chat/completions") > proxy_posts_before:
        break
    time.sleep(0.2)
os.kill(worker_b.pid, signal.SIGKILL)
worker_b.wait()

mid_status_b = psql("SELECT status FROM submissions WHERE id = %d;" % sub_b)
mid_v_b = psql("SELECT count(*) FROM verdicts WHERE submission_id = %d;" % sub_b)
print("  [intermediate state at SIGKILL (judge call in flight): status=%s, verdicts=%s]"
      % (mid_status_b, mid_v_b))

proc_b = run_worker_once()
final_status_b = psql("SELECT status FROM submissions WHERE id = %d;" % sub_b)
final_v_b = psql("SELECT count(*) FROM verdicts WHERE submission_id = %d;" % sub_b)
final_ev_b = psql("SELECT count(*) FROM events WHERE type = 'verdict.issued' "
                  "AND payload->>'submission_id' = '%d';" % sub_b)

ok_b = (
    mid_status_b == "grading" and mid_v_b == "0"
    and proc_b.returncode == 0
    and final_status_b == "graded" and final_v_b == "1" and final_ev_b == "1"
)
check("b", "kill mid-judge -> grading/0 verdicts, restart recovers to EXACTLY one verdict", ok_b,
      "killed: status=%s verdicts=%s | recovered: status=%s verdicts=%s events=%s"
      % (mid_status_b, mid_v_b, final_status_b, final_v_b, final_ev_b))


# ==============================================================================
# Check (c) Budget cutoff: exhausted student -> 429 path, no verdict-as-pass
# ==============================================================================
sub_c = seed_submission("dave@keel.test", "c3" * 20)
count_before_c = fake_count()
proc_c = run_worker_once()

status_c = psql("SELECT status FROM submissions WHERE id = %d;" % sub_c)
v_c = psql("SELECT count(*) FROM verdicts WHERE submission_id = %d;" % sub_c)
blocked_ev_c = psql("SELECT count(*) FROM events WHERE type = 'grade.budget_blocked' "
                    "AND payload->>'submission_id' = '%d';" % sub_c)
proxy_ev_c = psql("SELECT count(*) FROM events WHERE type = 'proxy.budget_exceeded' "
                  "AND payload->>'student_id' = "
                  "(SELECT id::text FROM students WHERE email = 'dave@keel.test');")
used_c = int(psql("SELECT b.tokens_used FROM budgets b JOIN students s ON s.id = b.student_id "
                  "WHERE s.email = 'dave@keel.test';"))

ok_c = (
    proc_c.returncode == 0
    and status_c == "error"
    and v_c == "0"
    and blocked_ev_c == "1"
    and int(proxy_ev_c) >= 1
    and fake_count() == count_before_c  # never forwarded upstream
    and used_c == 100                   # nothing charged
)
check("c", "exhausted budget -> 429 handled: status='error', grade.budget_blocked event, "
           "NO verdict row, nothing charged/forwarded, worker loop exits 0", ok_c,
      "status=%s verdicts=%s blocked_events=%s proxy_events=%s used=%d forwarded_delta=%d"
      % (status_c, v_c, blocked_ev_c, proxy_ev_c, used_c, fake_count() - count_before_c))


# ==============================================================================
# Check (d) Rubric-version flow: temp v2 picked up, then v1 restored
# ==============================================================================
try:
    v1_text = (REPO_ROOT / "content" / "rubrics" / "3.2.1" / "v1.yaml").read_text()
    RUBRIC_V2.write_text(v1_text.replace("version: 1", "version: 2", 1))
    if not RUBRIC_V2.exists():
        raise RuntimeError("v2 rubric creation failed")

    sub_d1 = seed_submission("alice@keel.test", "d4" * 20)
    proc_d1 = run_worker_once()
    version_d1 = psql("SELECT rubric_version FROM verdicts WHERE submission_id = %d;" % sub_d1)

    RUBRIC_V2.unlink()
    if RUBRIC_V2.exists():
        raise RuntimeError("v2 rubric deletion failed (still present)")

    sub_d2 = seed_submission("alice@keel.test", "e5" * 20)
    proc_d2 = run_worker_once()
    version_d2 = psql("SELECT rubric_version FROM verdicts WHERE submission_id = %d;" % sub_d2)

    ok_d = (
        proc_d1.returncode == 0 and proc_d2.returncode == 0
        and version_d1 == "2" and version_d2 == "1"
    )
    check("d", "rubric versioning: temp v2 -> fresh grade uses v2; v2 deleted -> v1 again "
               "(resolver drives verdicts, zero code edits)", ok_d,
          "with v2 on disk: version=%s | after deletion: version=%s" % (version_d1, version_d2))
finally:
    if RUBRIC_V2.exists():
        RUBRIC_V2.unlink()
    if RUBRIC_V2.exists():
        print("FAIL d: temp v2 rubric could not be removed", file=sys.stderr)
        failures.append("d-cleanup")


if failures:
    print("\nFAILED: %s" % ", ".join(failures))
    sys.exit(1)
