#!/usr/bin/env python3
"""platform/grading/scripts/smoke-recheck-checks.py: S3.3 spaced re-check scheduler checks.

Deterministic test battery (no sleeps; the clock is KEEL_PRACTICE_NOW_FILE):

1.  Deterministic clock honored: a pass at T0 stamps created_at from the knob.
2.  Pass at T0 -> schedule stage 1, 'upcoming' at T+2 -> 'due' at T+3.
3.  Due list at T+3 contains exactly the passed seed.
4.  Passing the re-check at T+3 advances to stage 2; nothing due until T+10.
5.  T+10 -> due again; completing it retires the seed (status 'retired',
    never due again, still retired at T+999).
6.  A FAILED re-check leaves the seed due (retry at will).
7.  Fail attempts never create or advance a schedule.
8.  An early pass (before the due instant) does not advance the stage.
9.  Multiple seeds schedule independently.
10. Unenrolled student: no schedule.
11. Malformed schedule requests fail honestly (400/401).
12. Gate/rebate/unlock isolation: engine + machine run, zero rows/events.
13. Token economics: per-drill tokens_charged <= 1500; the judge prompt
    carries the excerpt header with chars sent (auditable in the trace).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
GRADING_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str

SERVICE_URL = os.environ.get("KEEL_PRACTICE_URL", "http://127.0.0.1:8792")
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "smoke-recheck-secret")
TRACE_LOG_PATH = os.environ.get("KEEL_TRACE_LOG", str(Path.home() / ".keelacademy-traces.jsonl"))
NOW_FILE = os.environ.get("KEEL_RECHECK_NOW_FILE", "")
ENGINE = GRADING_DIR / "gates" / "engine.py"
MACHINE = GRADING_DIR / "rebate" / "machine.py"

UNIT = "3.2.1"
SEEDS = [
    "why free-text LLM output cannot be parsed reliably by downstream systems",
    "why schema-constrained generation beats prompt-promised JSON",
    "JSON mode vs tool-calling-style structured outputs: what each actually guarantees",
    "Pydantic v2 model_validate as an enforcement boundary, not just a dataclass",
    "graceful degradation: fallback objects and logged validation failures instead of silent drops",
]
PASS_ANSWER = (
    "Downstream programs need deterministic typed fields. Free-text model output "
    "varies with conversational phrasing, markdown fences, and trailing prose, so "
    "parsing it with json.loads or string splits fails or writes garbage downstream."
)
FAIL_ANSWER = "fail_me: the model just needs a nicer prompt, then json.loads always works."

T0 = "2026-03-01T09:00:00+00:00"

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  [PASS] {name}")
        PASS_COUNT += 1
    else:
        print(f"  [FAIL] {name} {detail}", file=sys.stderr)
        FAIL_COUNT += 1


def req(
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = APP_TOKEN,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Keel-App-Token"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(f"{SERVICE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def set_now(iso: str) -> None:
    if not NOW_FILE:
        raise RuntimeError("KEEL_RECHECK_NOW_FILE not set")
    Path(NOW_FILE).write_text(iso + "\n", encoding="utf-8")


def student_id_by_email(email: str) -> int:
    rows = db_sql(f"BEGIN;\nSELECT id FROM students WHERE email = {sql_str(email)};\nROLLBACK;\n")
    if not rows:
        raise RuntimeError(f"student not found: {email}")
    return int(rows[0][0])


def submit_retrieval(student_id: int, seed_index: int, answer: str) -> tuple[int, dict[str, Any]]:
    return req("/practice/retrieval/attempt", method="POST", body={
        "student_id": student_id,
        "unit_id": UNIT,
        "seed_index": seed_index,
        "seed_prompt": SEEDS[seed_index],
        "answer": answer,
    })


def schedule(student_id: int, unit: str | None = UNIT) -> dict[str, Any]:
    q = f"/practice/retrieval/schedule?student_id={student_id}"
    if unit:
        q += f"&unit={unit}"
    code, res = req(q)
    if code != 200:
        raise RuntimeError(f"schedule endpoint returned {code}: {res}")
    return res


def seed_state(sched: dict[str, Any], seed_index: int, unit: str = UNIT) -> dict[str, Any] | None:
    for s in sched.get("seeds", []):
        if s["seed_index"] == seed_index and s["unit_id"] == unit:
            return s
    return None


def main() -> int:
    alice_id = student_id_by_email("alice@keel.test")
    bob_id = student_id_by_email("bob@keel.test")
    carol_id = student_id_by_email("carol@keel.test")

    print("== 1. Deterministic clock honored on attempt persistence ==")
    set_now(T0)
    code, res = submit_retrieval(alice_id, 0, PASS_ANSWER)
    check("pass attempt on seed 0 returns 200 passed=true", code == 200 and res.get("passed") is True, f"got {code}: {res}")
    rows = db_sql(f"BEGIN;\nSELECT created_at::text FROM retrieval_attempts WHERE id = {res.get('attempt_id')};\nROLLBACK;\n")
    check("created_at stamped from deterministic clock (T0)",
          bool(rows) and rows[0][0].startswith("2026-03-01 09:00"), f"got {rows}")

    print("\n== 2. Pass -> upcoming at T+2, due at T+3 ==")
    sched = schedule(alice_id)
    check("schedule reports deterministic now", sched.get("now", "").startswith("2026-03-01T09:00"), f"got {sched.get('now')}")
    st = seed_state(sched, 0)
    check("seed 0 present at stage 1 upcoming right after pass",
          bool(st) and st["stage"] == 1 and st["status"] == "upcoming", f"got {st}")
    check("seed 0 due_at is T0 + 3 days",
          bool(st) and st["due_at"] and st["due_at"].startswith("2026-03-04T09:00"), f"got {st and st['due_at']}")
    check("due_count is 0 right after pass", sched.get("due_count") == 0, f"got {sched.get('due_count')}")

    set_now("2026-03-03T09:00:00+00:00")  # T+2
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("T+2: seed 0 still upcoming, nothing due",
          bool(st) and st["status"] == "upcoming" and sched.get("due_count") == 0, f"got {st}")

    set_now("2026-03-04T09:00:00+00:00")  # T+3
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("T+3: seed 0 is due", bool(st) and st["status"] == "due", f"got {st}")
    check("T+3: due_count is exactly 1", sched.get("due_count") == 1, f"got {sched.get('due_count')}")
    due_idxs = [s["seed_index"] for s in sched["seeds"] if s["status"] == "due"]
    check("T+3: the due seed is exactly seed 0", due_idxs == [0], f"got {due_idxs}")

    print("\n== 3. Early pass does not advance the stage ==")
    code, res = submit_retrieval(alice_id, 1, PASS_ANSWER)  # seed 1 first pass at T+3
    check("seed 1 first pass passes", code == 200 and res.get("passed") is True, f"got {code}")
    code, res = submit_retrieval(alice_id, 1, PASS_ANSWER)  # immediate re-pass, far before +3d
    check("seed 1 immediate re-pass passes", code == 200 and res.get("passed") is True, f"got {code}")
    sched = schedule(alice_id)
    st1 = seed_state(sched, 1)
    check("seed 1 still stage 1 (early pass did not advance)",
          bool(st1) and st1["stage"] == 1 and st1["status"] == "upcoming", f"got {st1}")
    check("seed 1 anchor stayed at the first pass (due T+6)",
          bool(st1) and st1["due_at"] and st1["due_at"].startswith("2026-03-07T09:00"), f"got {st1 and st1['due_at']}")

    print("\n== 4. Failed re-check leaves the seed due ==")
    code, res = submit_retrieval(alice_id, 0, FAIL_ANSWER)  # fail the due re-check on seed 0
    check("failed re-check returns 200 passed=false", code == 200 and res.get("passed") is False, f"got {code}: {res}")
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("seed 0 still due after failed re-check",
          bool(st) and st["stage"] == 1 and st["status"] == "due", f"got {st}")

    print("\n== 5. Passing the due re-check advances to stage 2 ==")
    code, res = submit_retrieval(alice_id, 0, PASS_ANSWER)
    check("re-check pass returns 200 passed=true", code == 200 and res.get("passed") is True, f"got {code}")
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("seed 0 advanced to stage 2 upcoming",
          bool(st) and st["stage"] == 2 and st["status"] == "upcoming", f"got {st}")
    check("seed 0 next due at last pass + 7 days (T+10)",
          bool(st) and st["due_at"] and st["due_at"].startswith("2026-03-11T09:00"), f"got {st and st['due_at']}")
    check("nothing due for alice now", sched.get("due_count") == 0, f"got {sched.get('due_count')}")

    set_now("2026-03-10T09:00:00+00:00")  # T+9
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("T+9: seed 0 still upcoming (nothing due until T+10)",
          bool(st) and st["status"] == "upcoming", f"got {st}")
    due_idxs = [s["seed_index"] for s in sched["seeds"] if s["status"] == "due"]
    check("T+9: only seed 1 is due (its first window opened at T+6)",
          due_idxs == [1], f"got due={due_idxs}")

    print("\n== 6. T+10: due again; completing retires the seed ==")
    set_now("2026-03-11T09:00:00+00:00")  # T+10
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("T+10: seed 0 due at stage 2", bool(st) and st["stage"] == 2 and st["status"] == "due", f"got {st}")
    code, res = submit_retrieval(alice_id, 0, PASS_ANSWER)
    check("final re-check pass returns 200 passed=true", code == 200 and res.get("passed") is True, f"got {code}")
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("seed 0 retired after second re-check pass",
          bool(st) and st["stage"] == 3 and st["status"] == "retired" and st["due_at"] is None, f"got {st}")
    due_idxs = [s["seed_index"] for s in sched["seeds"] if s["status"] == "due"]
    check("retired seed not counted due; only seed 1 (opened at T+6, unworked) remains",
          due_idxs == [1] and sched.get("due_count") == 1, f"got due={due_idxs}")

    set_now("2027-01-01T00:00:00+00:00")  # far future
    sched = schedule(alice_id)
    st = seed_state(sched, 0)
    check("T+999: seed 0 remains retired, never due again",
          bool(st) and st["status"] == "retired" and st["due_at"] is None, f"got {st}")
    check("history kept: seed 0 still listed with last_pass_at",
          bool(st) and bool(st.get("last_pass_at")), f"got {st}")
    due_idxs = [s["seed_index"] for s in sched["seeds"] if s["status"] == "due"]
    check("T+999: an unworked overdue seed stays due (honest, retry at will)",
          due_idxs == [1] and sched.get("due_count") == 1, f"got due={due_idxs}")

    print("\n== 7. Fail attempts never create a schedule ==")
    set_now(T0)
    code, res = submit_retrieval(alice_id, 2, FAIL_ANSWER)
    check("fail attempt on seed 2 returns passed=false", code == 200 and res.get("passed") is False, f"got {code}")
    sched = schedule(alice_id)
    check("seed 2 has no schedule entry after only fails", seed_state(sched, 2) is None,
          f"got {seed_state(sched, 2)}")

    print("\n== 8. Multiple seeds schedule independently ==")
    set_now("2026-03-07T09:00:00+00:00")  # T+6: seed 1 first re-check due
    sched = schedule(alice_id)
    st0 = seed_state(sched, 0)
    st1 = seed_state(sched, 1)
    check("T+6: seed 0 folded to retired from full history (never surfaces as due)",
          bool(st0) and st0["status"] == "retired", f"got {st0}")
    check("T+6: seed 1 is due at stage 1",
          bool(st1) and st1["stage"] == 1 and st1["status"] == "due", f"got {st1}")
    check("T+6: seed 2 (fail-only) has no entry", seed_state(sched, 2) is None)
    check("T+6: due_count counts exactly seed 1", sched.get("due_count") == 1, f"got {sched.get('due_count')}")

    print("\n== 9. Unenrolled and idle students have no schedule ==")
    sched = schedule(carol_id)
    check("unenrolled carol: zero seeds, zero due",
          sched.get("seeds") == [] and sched.get("due_count") == 0, f"got {sched}")
    sched = schedule(bob_id)
    check("enrolled bob with no attempts: zero seeds, zero due",
          sched.get("seeds") == [] and sched.get("due_count") == 0, f"got {sched}")
    check("unenrolled carol attempt rejected 403",
          submit_retrieval(carol_id, 0, PASS_ANSWER)[0] == 403)
    carol_rows = db_sql(f"BEGIN;\nSELECT count(*) FROM retrieval_attempts WHERE student_id = {carol_id};\nROLLBACK;\n")
    check("zero retrieval rows for carol", carol_rows[0][0] == "0", f"got {carol_rows}")

    print("\n== 10. Schedule endpoint honesty ==")
    code, _ = req("/practice/retrieval/schedule?student_id=abc")
    check("non-integer student_id rejected 400", code == 400, f"got {code}")
    code, _ = req(f"/practice/retrieval/schedule?student_id={alice_id}&unit=bad")
    check("bad unit format rejected 400", code == 400, f"got {code}")
    code, _ = req(f"/practice/retrieval/schedule?student_id={alice_id}", token=None)
    check("missing app token rejected 401", code == 401, f"got {code}")
    set_now("2026-03-07T09:00:00+00:00")
    code, res = req(f"/practice/retrieval/schedule?student_id={alice_id}")
    check("unit-less schedule spans units and matches per-unit view",
          code == 200 and any(s["unit_id"] == UNIT for s in res.get("seeds", [])), f"got {code}")

    print("\n== 11. Practice events never touch gates, rebates, or unlocks ==")
    env = os.environ.copy()
    env["KEEL_GATE_ONCE"] = "1"
    env["KEEL_REBATE_ONCE"] = "1"
    subprocess.run([sys.executable, str(ENGINE)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(MACHINE)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    unlocked = db_sql("BEGIN;\nSELECT count(*) FROM unlocked_units;\nROLLBACK;\n")[0][0]
    rebates = db_sql("BEGIN;\nSELECT count(*) FROM rebates;\nROLLBACK;\n")[0][0]
    gate_passed = db_sql("BEGIN;\nSELECT count(*) FROM events WHERE type = 'gate.passed';\nROLLBACK;\n")[0][0]
    gate_pledged = db_sql("BEGIN;\nSELECT count(*) FROM events WHERE type = 'gate.pledged';\nROLLBACK;\n")[0][0]
    check("zero unlocked_units rows", unlocked == "0", f"got {unlocked}")
    check("zero rebates rows", rebates == "0", f"got {rebates}")
    check("zero gate.passed events", gate_passed == "0", f"got {gate_passed}")
    check("zero gate.pledged events", gate_pledged == "0", f"got {gate_pledged}")

    print("\n== 12. Drill token economics (S3.3 carried finding) ==")
    set_now(T0)
    code, res = submit_retrieval(alice_id, 3, PASS_ANSWER)
    check("economics probe attempt grades pass", code == 200 and res.get("passed") is True, f"got {code}")
    charged = int(res.get("tokens_charged", 0))
    check("per-drill tokens_charged <= 1500 (target)", 0 < charged <= 1500, f"got {charged}")
    excerpt = res.get("excerpt") or {}
    check("response carries excerpt metadata with chars sent",
          0 < int(excerpt.get("excerpt_chars", 0)) < int(excerpt.get("lesson_chars", 0)),
          f"got {excerpt}")
    vj = db_sql(f"BEGIN;\nSELECT verdict_json::text FROM retrieval_attempts WHERE id = {res.get('attempt_id')};\nROLLBACK;\n")
    vj_excerpt = (json.loads(vj[0][0]).get("excerpt") or {}) if vj else {}
    check("persisted verdict_json carries excerpt metadata",
          int(vj_excerpt.get("excerpt_chars", 0)) == int(excerpt.get("excerpt_chars", -1)),
          f"got {vj_excerpt}")

    trace_records = []
    trace_file = Path(TRACE_LOG_PATH)
    if trace_file.is_file():
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if rec.get("caller") == "retrieval":
                    trace_records.append(rec)
            except Exception:
                pass
    check("trace log has retrieval records", len(trace_records) > 0, f"count={len(trace_records)}")
    if trace_records:
        last = trace_records[-1]
        prompt_text = "\n".join(str(m.get("content", "")) for m in last.get("prompt", []))
        check("trace prompt carries excerpt header with chars sent",
              "Lesson Material (excerpt:" in prompt_text and "chars" in prompt_text)
        check("trace prompt keeps the student_answer delimiting",
              "<student_answer>" in prompt_text and "</student_answer>" in prompt_text)

    print(f"\n== SMOKE RECHECK CHECKS COMPLETE: {PASS_COUNT} passed, {FAIL_COUNT} failed ==")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

