#!/usr/bin/env python3
"""platform/grading/worker.py — Job queue worker for grading submissions (S1.3, wired S1.8).

Consumes queued submissions from PostgreSQL and writes exactly-once verdicts,
surviving crashes, restarts, and concurrent duplicates.

Stdlib only. The GRADE step shells out to the two grading layers:
  Layer 1  platform/grading/layer1.py — deterministic checks through the S1.4
           hardened sandbox runner (one container per check).
  Layer 2  platform/cli grader.judge — rubric judging via the LLM, routed
           through the S1.5 budget proxy when KEEL_PROXY_URL is set. The
           judge subprocess gets KEEL_LLM_BASE_URL=<proxy>/v1 and
           KEEL_LLM_STUDENT_ID=<submission's student>, so per-student token
           budgets apply to grading calls.

Submission files: env KEEL_SUBMISSIONS_DIR names a directory laid out
<KEEL_SUBMISSIONS_DIR>/<submission_id>/ containing the checked-out submission
(the intake/checkout stage places it there; smoke harnesses seed it). When
KEEL_SUBMISSIONS_DIR is unset the worker falls back to the S1.3 deterministic
sha-parity stub so the S1.3 proof harness keeps running without docker/LLM
plumbing.

Budget-blocked outcome (documented choice): when the proxy answers 429
budget_exceeded, the submission gets status='error' and a
'grade.budget_blocked' event, and NO verdict row is written — budget
exhaustion is not a grading outcome, and leaving the verdict slot free means a
regrade after a budget top-up still lands on exactly one verdict via the
unchanged ON CONFLICT path.

Rubric versioning: the active rubric is resolved per grade with
grader.rubric_version.resolve_active_rubric (subprocess; the worker stays
stdlib), so rubric edits flow into verdicts with zero code changes.

Traceability: each judge subprocess runs with KEEL_TRACE_CALLER=worker,
KEEL_TRACE_CALL_ID=sub-<id>-<uuid>, KEEL_TRACE_LOG passthrough; the verdict
JSON carries the matching S1.7 trace records.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Add parent directory to sys.path to import shared db module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import db_cmd, db_sql, sql_str

GRADING_DIR = Path(__file__).resolve().parent
LAYER1 = GRADING_DIR / "layer1.py"
CLI_DIR = GRADING_DIR.parent / "cli"  # platform/cli, home of the grader package


class GradeError(Exception):
    pass


class BudgetBlocked(Exception):
    pass


def grade_stub(commit_sha: str) -> dict:
    """Deterministic stub grade step (S1.3 fallback; used when
    KEEL_SUBMISSIONS_DIR is unset).

    Pass if sha256(commit_sha) is even, else fail.
    Sleeps KEEL_GRADE_SLEEP_S (default 1.0) to simulate grading work and allow
    testing of crash/kill windows.
    """
    sleep_s = float(os.environ.get("KEEL_GRADE_SLEEP_S", "1"))
    if sleep_s > 0:
        time.sleep(sleep_s)

    h = hashlib.sha256(commit_sha.encode("utf-8")).hexdigest()
    is_even = (int(h, 16) % 2 == 0)
    overall = "pass" if is_even else "fail"
    return {
        "overall": overall,
        "criteria": [],
        "stub": True,
    }


def resolve_active_rubric(unit_id: str) -> Path:
    """Resolve via the real resolver (platform/cli grader.rubric_version) so
    the worker never re-implements the rule."""
    proc = subprocess.run(
        [sys.executable, "-m", "grader.rubric_version", unit_id],
        cwd=CLI_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise GradeError("rubric resolution failed for %r: %s"
                         % (unit_id, proc.stderr.decode(errors="replace").strip()))
    return Path(proc.stdout.decode().strip())


def run_layer1(submission_dir: Path, unit_id: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(LAYER1), "--submission", str(submission_dir),
         "--unit", unit_id],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise GradeError("layer1 failed: %s" % proc.stderr.decode(errors="replace").strip()[-500:])
    return json.loads(proc.stdout.decode().strip().splitlines()[-1])


def collect_trace_records(trace_log: str, call_id: str) -> list:
    """Read the S1.7 trace log and return the records stamped with this
    grading call's correlation id (never the prompts/responses themselves —
    the verdict keeps only the bookkeeping fields)."""
    records = []
    try:
        with open(trace_log, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("call_id") == call_id:
                    records.append({
                        k: rec[k] for k in
                        ("ts", "caller", "model", "tier", "attempt", "latency_s",
                         "prompt_tokens", "completion_tokens", "cost_usd")
                        if k in rec
                    })
    except OSError:
        pass
    return records


def run_judge(submission_dir: Path, rubric_path: Path, student_id: int, call_id: str) -> dict:
    """Run the Layer-2 judge, routed through the proxy when configured.

    Returns the judge verdict dict. Raises BudgetBlocked when the judge exits
    3 (proxy answered 429 budget_exceeded) and GradeError otherwise.
    """
    env = os.environ.copy()
    env["KEEL_TRACE_CALLER"] = "worker"
    env["KEEL_TRACE_CALL_ID"] = call_id
    env["KEEL_LLM_STUDENT_ID"] = str(student_id)
    proxy_url = os.environ.get("KEEL_PROXY_URL")
    if proxy_url:
        env["KEEL_LLM_BASE_URL"] = proxy_url.rstrip("/") + "/v1"
    else:
        env.pop("KEEL_LLM_BASE_URL", None)
        env.pop("KEEL_LLM_STUDENT_ID", None)  # direct calls carry no student header
    with tempfile.NamedTemporaryFile(
        mode="r", suffix=".json", prefix="keel-verdict-", delete=False
    ) as tf:
        verdict_path = tf.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "grader.judge", str(submission_dir),
             "--rubric", str(rubric_path), "--json", verdict_path],
            cwd=CLI_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if proc.returncode == 3:
            raise BudgetBlocked(proc.stderr.decode(errors="replace").strip()[-500:])
        if proc.returncode != 0:
            raise GradeError("judge failed (exit %d): %s"
                             % (proc.returncode,
                                proc.stderr.decode(errors="replace").strip()[-500:]))
        with open(verdict_path, encoding="utf-8") as fh:
            return json.load(fh)
    finally:
        os.unlink(verdict_path)


def grade_real(sub_id: int, student_id: int, unit_id: str, submission_dir: Path) -> dict:
    """Full two-layer grade for one submission. Returns verdict data with
    overall + rubric identity; raises BudgetBlocked/GradeError."""
    layer1 = run_layer1(submission_dir, unit_id)

    sleep_s = float(os.environ.get("KEEL_GRADE_SLEEP_S", "1"))
    if sleep_s > 0:
        # Crash-window knob (kept from S1.3): a deterministic pause right
        # before the judge call so kill-mid-judge proofs have a window.
        time.sleep(sleep_s)

    rubric_path = resolve_active_rubric(unit_id)
    call_id = "sub-%d-%s" % (sub_id, uuid.uuid4().hex[:8])
    judge_verdict = run_judge(submission_dir, rubric_path, student_id, call_id)

    trace_log = os.environ.get("KEEL_TRACE_LOG", "")
    return {
        "overall": judge_verdict["overall"],
        "rubric_id": judge_verdict["rubric_id"],
        "rubric_version": judge_verdict["rubric_version"],
        "layer1": layer1,
        "judge": judge_verdict,
        "trace": {
            "log": trace_log or None,
            "call_id": call_id,
            "records": collect_trace_records(trace_log, call_id),
        },
    }


def claim_submission():
    """Atomically claim one queued submission using SELECT FOR UPDATE SKIP LOCKED.

    Flips status queued -> grading in a single transaction and returns the claimed row.
    Two concurrent workers will never claim the same row.
    """
    sql = """BEGIN;
WITH next_sub AS (
    SELECT id
    FROM submissions
    WHERE status = 'queued'
    ORDER BY id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE submissions s
SET status = 'grading'
FROM next_sub
WHERE s.id = next_sub.id
RETURNING s.id, s.student_id, s.unit_id, s.commit_sha, s.repo_url;
COMMIT;
"""
    rows = db_sql(sql)
    if not rows:
        return None
    return rows[0]


def write_verdict(sub_id: int, rubric_id: str, rubric_version: int,
                  overall: str, verdict_data: dict) -> tuple[int, str, dict]:
    """Write verdict to database with ON CONFLICT DO NOTHING.

    If inserted -> this worker won.
    If conflict -> another attempt or concurrent worker already wrote the verdict:
    read it back, reconcile, and treat as already-graded.
    """
    verdict_json_str = json.dumps(verdict_data)

    sql_insert = """BEGIN;
INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
VALUES (%d, %s, %d, %s, %s::jsonb)
ON CONFLICT (submission_id) DO NOTHING
RETURNING id, overall, verdict_json;
COMMIT;
""" % (
        sub_id,
        sql_str(rubric_id),
        int(rubric_version),
        sql_str(overall),
        sql_str(verdict_json_str),
    )

    rows = db_sql(sql_insert)
    if rows:
        verdict_id = int(rows[0][0])
        res_overall = rows[0][1]
        res_json = json.loads(rows[0][2])
        return verdict_id, res_overall, res_json

    # Conflict occurred: read back existing verdict
    sql_select = """BEGIN;
SELECT id, overall, verdict_json
FROM verdicts
WHERE submission_id = %d;
COMMIT;
""" % sub_id
    rows = db_sql(sql_select)
    if not rows:
        raise RuntimeError("Verdict insert conflicted but existing row could not be read")
    verdict_id = int(rows[0][0])
    res_overall = rows[0][1]
    res_json = json.loads(rows[0][2])
    return verdict_id, res_overall, res_json


def finish_submission(sub_id: int, student_id: int, unit_id: str, commit_sha: str,
                      verdict_id: int, overall: str, verdict_data: dict):
    """Idempotently update submission status to 'graded' and append 'verdict.issued' event.

    Single transaction. Appends verdict.issued ONLY IF no verdict.issued event with this
    submission_id exists yet (WHERE NOT EXISTS on payload->>'submission_id').
    """
    payload = {
        "submission_id": int(sub_id),
        "student_id": int(student_id),
        "unit_id": str(unit_id),
        "commit_sha": str(commit_sha),
        "overall": str(overall),
        "verdict_id": int(verdict_id),
    }
    payload_str = json.dumps(payload)

    sql = """BEGIN;
UPDATE submissions
SET status = 'graded'
WHERE id = %d;

INSERT INTO events (type, payload)
SELECT 'verdict.issued',
       %s::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM events
    WHERE type = 'verdict.issued'
      AND payload->>'submission_id' = %s
);
COMMIT;
""" % (
        sub_id,
        sql_str(payload_str),
        sql_str(str(sub_id)),
    )
    db_sql(sql, want_rows=False)


def reap_stale(stale_after_s: float):
    """Requeue or recover stale claims before claiming each loop.

    1. Submissions in status 'grading' WITH an existing verdict -> recover via finish path.
    2. Submissions in status 'grading' older than stale_after_s with NO verdict -> reset to 'queued'.
    """
    # 1. Recover grading submissions that already have a verdict (e.g. killed after write, before finish)
    sql_with_verdict = """BEGIN;
SELECT s.id, s.student_id, s.unit_id, s.commit_sha, v.id, v.overall, v.verdict_json
FROM submissions s
JOIN verdicts v ON v.submission_id = s.id
WHERE s.status = 'grading';
COMMIT;
"""
    rows = db_sql(sql_with_verdict)
    for r in rows:
        s_id, s_student, s_unit, s_sha, v_id, v_overall, v_json_raw = r
        v_data = json.loads(v_json_raw) if isinstance(v_json_raw, str) else v_json_raw
        finish_submission(int(s_id), int(s_student), s_unit, s_sha, int(v_id), v_overall, v_data)

    # 2. Reset stale grading submissions without verdicts back to 'queued'
    sql_stale = """BEGIN;
UPDATE submissions
SET status = 'queued'
WHERE status = 'grading'
  AND created_at <= now() - (%f * interval '1 second')
  AND NOT EXISTS (
      SELECT 1 FROM verdicts
      WHERE submission_id = submissions.id
  );
COMMIT;
""" % float(stale_after_s)
    db_sql(sql_stale, want_rows=False)


def budget_block(sub_id: int, student_id: int, unit_id: str, detail: str):
    """Budget-blocked outcome: status='error' + one grade.budget_blocked event,
    no verdict row (see module docstring for the rationale)."""
    payload = json.dumps({
        "submission_id": int(sub_id),
        "student_id": int(student_id),
        "unit_id": str(unit_id),
        "detail": detail,
    })
    db_sql(
        "BEGIN;\n"
        "UPDATE submissions SET status = 'error' WHERE id = %d;\n"
        "INSERT INTO events (type, payload) VALUES ("
        "'grade.budget_blocked', %s::jsonb);\n"
        "COMMIT;\n" % (sub_id, sql_str(payload)),
        want_rows=False,
    )


def process_submission(row):
    """Full lifecycle for one claimed submission: grade -> write -> finish."""
    sub_id_str, student_id_str, unit_id, commit_sha, repo_url = row
    sub_id = int(sub_id_str)
    student_id = int(student_id_str)

    submissions_dir = os.environ.get("KEEL_SUBMISSIONS_DIR")
    if not submissions_dir:
        # S1.3 stub mode: no submission files on disk, no layers to run.
        verdict_data = grade_stub(commit_sha)
        rubric_id, rubric_version = "stub-%s" % unit_id, 1
    else:
        submission_dir = Path(submissions_dir) / str(sub_id)
        if not submission_dir.is_dir():
            raise GradeError("submission dir not found: %s" % submission_dir)
        try:
            verdict_data = grade_real(sub_id, student_id, unit_id, submission_dir)
        except BudgetBlocked as exc:
            budget_block(sub_id, student_id, unit_id, str(exc))
            sys.stderr.write("worker: submission %s budget-blocked: %s\n" % (sub_id, exc))
            return
        rubric_id = verdict_data["rubric_id"]
        rubric_version = verdict_data["rubric_version"]

    verdict_id, overall, verdict_data = write_verdict(
        sub_id, rubric_id, rubric_version, verdict_data["overall"], verdict_data
    )
    finish_submission(
        sub_id, student_id, unit_id, commit_sha, verdict_id, overall, verdict_data
    )


def run_worker():
    once = os.environ.get("KEEL_WORKER_ONCE", "0").lower() in ("1", "true", "yes")
    stale_after_s = float(os.environ.get("KEEL_STALE_AFTER_S", "300"))
    poll_interval_s = float(os.environ.get("KEEL_POLL_INTERVAL_S", "0.5"))

    # Fail fast on database connection error
    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)

    while True:
        try:
            reap_stale(stale_after_s)
        except Exception as e:
            sys.stderr.write("worker: reaper error: %s\n" % e)

        try:
            row = claim_submission()
        except Exception as e:
            sys.stderr.write("worker: claim error: %s\n" % e)
            if once:
                break
            time.sleep(poll_interval_s)
            continue

        if row is None:
            if once:
                break
            time.sleep(poll_interval_s)
            continue

        try:
            process_submission(row)
        except Exception as e:
            sub_id = row[0]
            sys.stderr.write("worker: error processing submission %s: %s\n" % (sub_id, e))
            try:
                db_sql(
                    "BEGIN;\nUPDATE submissions SET status = 'error' WHERE id = %d;\nCOMMIT;\n"
                    % int(sub_id),
                    want_rows=False,
                )
            except Exception as db_err:
                sys.stderr.write("worker: failed to set status='error' for submission %s: %s\n" % (sub_id, db_err))


if __name__ == "__main__":
    run_worker()
