#!/usr/bin/env python3
"""smoke-wiring-live-checks.py — gated LIVE wiring check (stdlib only).

One REAL judge call: a fresh golden submission graded through a proxy whose
upstream is the real OpenAI API. Asserts a verdict row exists, the judge
verdict carries real model metadata, the trace log has a worker-tagged record
with real token counts, and the student's budget was charged for exactly the
real usage. Run only with KEEL_WIRING_LIVE=1 and OPENAI_API_KEY in env
(cost: one mid-tier call over the golden submission, typically < $0.05).
"""

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

DOCKER = os.environ["WIRING_DOCKER"]
CONTAINER = os.environ["WIRING_CONTAINER"]
DB_USER = os.environ["WIRING_DB_USER"]
DB_NAME = os.environ["WIRING_DB_NAME"]
DB_CMD = os.environ["WIRING_DB_CMD"]
WORKER_SCRIPT = os.environ["WIRING_WORKER"]
SUBS_DIR = Path(os.environ["WIRING_SUBS_DIR"])
TRACE_LOG = Path(os.environ["WIRING_TRACE_LOG"])
REPO_ROOT = Path(os.environ.get("WIRING_REPO_ROOT", SUBS_DIR))


def psql(sql: str) -> str:
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-q", "-tA", "-F", "\t", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return out.stdout.decode("utf-8").strip()


sub_id = int(psql(
    "INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, pusher_email, status) "
    "SELECT id, '3.2.1', '%s', 'https://github.com/keel-academy/keel-3.2.1.git', "
    "'alice@keel.test', 'queued' FROM students WHERE email = 'alice@keel.test' RETURNING id;"
    % ("f6" * 20)))
sub_dir = SUBS_DIR / str(sub_id)
shutil.copytree(REPO_ROOT / "content" / "golden" / "3.2.1" / "s01-textbook", sub_dir)
shutil.copy(REPO_ROOT / "content" / "golden" / "3.2.1" / "s14-artifact-evidence" / "claims_messy.jsonl",
            sub_dir / "claims_messy.jsonl")

env = os.environ.copy()
env["KEEL_DB_CMD"] = DB_CMD
env["KEEL_WORKER_ONCE"] = "1"
proc = subprocess.run([sys.executable, WORKER_SCRIPT], env=env,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

row = psql("SELECT s.status, v.rubric_id, v.rubric_version, v.overall, v.verdict_json "
           "FROM submissions s JOIN verdicts v ON v.submission_id = s.id WHERE s.id = %d;" % sub_id)
status, rubric_id, version, overall, vjson_raw = row.split("\t", 4)
vj = json.loads(vjson_raw)
model = vj["judge"]["meta"].get("model", "")
tokens = vj["judge"]["meta"].get("prompt_tokens", 0) + vj["judge"]["meta"].get("completion_tokens", 0)
trace_recs = vj.get("trace", {}).get("records", [])
used = int(psql("SELECT b.tokens_used FROM budgets b JOIN students s ON s.id = b.student_id "
                "WHERE s.email = 'alice@keel.test';"))

ok = (
    proc.returncode == 0 and status == "graded"
    and rubric_id == "rubric-3.2.1" and version == "1"
    and overall in ("pass", "fail")
    and model and not model.startswith("fake")
    and tokens > 0
    and used >= tokens
    and trace_recs and trace_recs[0].get("caller") == "worker"
)
print("%s live: real judge call through proxy -> verdict (overall=%s, model=%s, %d tokens, "
      "budget used=%d, trace caller=%s)"
      % ("PASS" if ok else "FAIL", overall, model, tokens, used,
         trace_recs[0].get("caller") if trace_recs else None))
sys.exit(0 if ok else 1)
