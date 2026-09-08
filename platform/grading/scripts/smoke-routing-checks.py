#!/usr/bin/env python3
"""platform/grading/scripts/smoke-routing-checks.py: S3.4 adaptive routing checks.

Deterministic test battery (no sleeps; the clock is KEEL_PRACTICE_NOW_FILE):

1.  Fresh enrolled student: route = drills current, worked example recommended-later.
2.  Any single failed drill: scaffold route active with the CORRECT deep link for that seed.
3.  Retry-pass on failed seed: route advances, active scaffold cleared.
4.  Clean first-try sweep of all seeds: worked example OPTIONAL (fast pass active), completion current.
5.  Failed completion attempt: scaffold route for completion gap (worked example review).
6.  Completion pass: route complete, next recommended action = build deliverable.
7.  S3.3 due-ness independence: seeds becoming due at T+3/T+7 does NOT alter route status.
8.  Unenrolled student: honest empty route state (enrolled: false).
9.  No routing rules file: loud refusal (HTTP 404 routing_rules_not_found), never a silent default.
10. Validator negative probes: bad routing rules file rejected and named by validate-routing.py.
11. Gate/rebate/unlock isolation: zero rows in unlocked_units and rebates.
12. Pure read path: assert table counts are 100% unchanged through route queries.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
GRADING_DIR = SCRIPT_DIR.parent
REPO_ROOT = GRADING_DIR.parent.parent

sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str

SERVICE_URL = os.environ.get("KEEL_PRACTICE_URL", "http://127.0.0.1:8792")
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "smoke-routing-secret")
NOW_FILE = os.environ.get("KEEL_ROUTING_NOW_FILE", "")
ENGINE = GRADING_DIR / "gates" / "engine.py"
MACHINE = GRADING_DIR / "rebate" / "machine.py"
VALIDATE_ROUTING = REPO_ROOT / "content" / "tools" / "validate-routing.py"

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


def student_id(email: str) -> int:
    rows = db_sql("SELECT id FROM students WHERE email = %s;" % sql_str(email))
    assert rows, f"student {email} not found"
    return int(rows[0][0])


def set_now(iso_instant: str) -> None:
    if NOW_FILE:
        Path(NOW_FILE).write_text(iso_instant.strip() + "\n", encoding="utf-8")


def get_db_counts() -> dict[str, int]:
    sql = """BEGIN;
SELECT 'students', count(*) FROM students
UNION ALL SELECT 'enrollments', count(*) FROM enrollments
UNION ALL SELECT 'budgets', count(*) FROM budgets
UNION ALL SELECT 'retrieval_attempts', count(*) FROM retrieval_attempts
UNION ALL SELECT 'practice_attempts', count(*) FROM practice_attempts
UNION ALL SELECT 'events', count(*) FROM events
UNION ALL SELECT 'unlocked_units', count(*) FROM unlocked_units
UNION ALL SELECT 'rebates', count(*) FROM rebates;
ROLLBACK;
"""
    rows = db_sql(sql)
    return {r[0]: int(r[1]) for r in rows}


def main() -> int:
    print("== 1. fresh enrolled student: route = drills current, worked example recommended-later ==")
    alice_id = student_id("alice@keel.test")
    bob_id = student_id("bob@keel.test")
    carol_id = student_id("carol@keel.test")

    set_now(T0)

    code, route = req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
    check("fresh enrolled student returns HTTP 200", code == 200, f"got {code}")
    check("route status is in_progress", route.get("status") == "in_progress", str(route))
    check("recommended step is retrieval", route.get("recommended_step") == "retrieval", str(route))
    check("fast pass is eligible but not active", route.get("fast_pass_eligible") is True and route.get("fast_pass_active") is False)
    check("scaffold is not active", route.get("scaffold_active") is False)
    check("scaffold callout is null", route.get("scaffold_callout") is None)

    steps = {s["id"]: s for s in route.get("steps", [])}
    check("4 steps present in route", len(steps) == 4)
    check("lesson is done", steps.get("lesson", {}).get("status") == "done")
    check("retrieval is current with 0/5 passed", steps.get("retrieval", {}).get("status") == "current" and steps.get("retrieval", {}).get("passed_count") == 0)
    check("worked example is upcoming", steps.get("worked_example", {}).get("status") == "upcoming")
    check("completion is upcoming", steps.get("completion", {}).get("status") == "upcoming")

    print("\n== 2. single failed drill: scaffold route active with correct deep link ==")
    # Bob fails drill question 1 (seed index 1: schema-constrained generation vs prompt-promised JSON)
    fail_body = {
        "student_id": bob_id,
        "unit_id": UNIT,
        "seed_index": 1,
        "seed_prompt": SEEDS[1],
        "answer": FAIL_ANSWER,
    }
    c_att, r_att = req("/practice/retrieval/attempt", method="POST", body=fail_body)
    check("bob fails seed 1 via HTTP 200", c_att == 200 and r_att.get("passed") is False)

    code, bob_route = req(f"/practice/route?student_id={bob_id}&unit={UNIT}")
    check("bob route returns HTTP 200", code == 200)
    check("bob status is scaffold_active", bob_route.get("status") == "scaffold_active", str(bob_route))
    check("bob recommended step is worked_example", bob_route.get("recommended_step") == "worked_example", str(bob_route))
    check("fast pass is no longer eligible", bob_route.get("fast_pass_eligible") is False)
    check("scaffold is active", bob_route.get("scaffold_active") is True)

    bob_steps = {s["id"]: s for s in bob_route.get("steps", [])}
    check("bob retrieval step shows retry", bob_steps.get("retrieval", {}).get("status") == "retry")
    check("bob worked example step shows scaffold", bob_steps.get("worked_example", {}).get("status") == "scaffold")

    callout = bob_route.get("scaffold_callout")
    check("scaffold callout exists", callout is not None)
    check("scaffold callout targets seed 1", callout.get("seed_index") == 1)
    check("scaffold deep link target file is llm.py", callout.get("target_file") == "llm.py", str(callout))
    check("scaffold deep link anchor is worked-example", callout.get("anchor") == "worked-example")
    check("scaffold deep link url is /units/3.2.1#worked-example", callout.get("url") == f"/units/{UNIT}#worked-example")
    check("scaffold action label is present", "Review" in str(callout.get("action_label")))

    # Verify scaffold deep link mappings for all 5 seeds
    mapping = bob_route.get("scaffold_mapping", [])
    check("scaffold mapping includes all 5 seeds", len(mapping) == 5)
    check("seed 0 maps to extractor.py", mapping[0].get("target_file") == "extractor.py", str(mapping[0]))
    check("seed 1 maps to llm.py", mapping[1].get("target_file") == "llm.py", str(mapping[1]))
    check("seed 2 maps to llm.py", mapping[2].get("target_file") == "llm.py", str(mapping[2]))
    check("seed 3 maps to schemas.py", mapping[3].get("target_file") == "schemas.py", str(mapping[3]))
    check("seed 4 maps to extractor.py", mapping[4].get("target_file") == "extractor.py", str(mapping[4]))

    print("\n== 3. retry-pass on failed seed: route advances, scaffold cleared ==")
    # Bob passes seeds 0..4 (including retrying seed 1 to pass)
    for idx, prompt in enumerate(SEEDS):
        pass_body = {
            "student_id": bob_id,
            "unit_id": UNIT,
            "seed_index": idx,
            "seed_prompt": prompt,
            "answer": PASS_ANSWER,
        }
        c, r = req("/practice/retrieval/attempt", method="POST", body=pass_body)
        assert c == 200 and r.get("passed") is True

    code, bob_route2 = req(f"/practice/route?student_id={bob_id}&unit={UNIT}")
    check("bob route after retry passes returns HTTP 200", code == 200)
    check("bob status is standard (not fast pass due to prior fail)", bob_route2.get("status") == "standard", str(bob_route2))
    check("bob fast pass is not active", bob_route2.get("fast_pass_active") is False)
    check("bob scaffold is cleared (active = false)", bob_route2.get("scaffold_active") is False)
    check("bob scaffold callout is null", bob_route2.get("scaffold_callout") is None)
    check("bob recommended step is worked_example", bob_route2.get("recommended_step") == "worked_example")

    bob_steps2 = {s["id"]: s for s in bob_route2.get("steps", [])}
    check("bob retrieval step is done (5/5)", bob_steps2.get("retrieval", {}).get("status") == "done" and bob_steps2.get("retrieval", {}).get("passed_count") == 5)
    check("bob worked example step is current (standard path)", bob_steps2.get("worked_example", {}).get("status") == "current")
    check("bob completion step is upcoming", bob_steps2.get("completion", {}).get("status") == "upcoming")

    print("\n== 4. clean first-try sweep of all seeds: worked example OPTIONAL (fast pass active) ==")
    # Alice passes all seeds 0..4 on first try with zero fails
    for idx, prompt in enumerate(SEEDS):
        pass_body = {
            "student_id": alice_id,
            "unit_id": UNIT,
            "seed_index": idx,
            "seed_prompt": prompt,
            "answer": PASS_ANSWER,
        }
        c, r = req("/practice/retrieval/attempt", method="POST", body=pass_body)
        assert c == 200 and r.get("passed") is True

    code, alice_route = req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
    check("alice route returns HTTP 200", code == 200)
    check("alice status is fast_pass", alice_route.get("status") == "fast_pass", str(alice_route))
    check("alice fast_pass_active is True", alice_route.get("fast_pass_active") is True)
    check("alice recommended step jumps to completion", alice_route.get("recommended_step") == "completion")

    alice_steps = {s["id"]: s for s in alice_route.get("steps", [])}
    check("alice retrieval step is done", alice_steps.get("retrieval", {}).get("status") == "done")
    check("alice worked example step is OPTIONAL", alice_steps.get("worked_example", {}).get("status") == "optional")
    check("alice completion step is CURRENT", alice_steps.get("completion", {}).get("status") == "current")

    print("\n== 5. failed completion attempt: scaffold route for completion gap ==")
    # Bob attempts completion problem with unfilled base files (fails checks)
    comp_base_dir = REPO_ROOT / "content" / "units" / "phase-3" / "3.2.1" / "completion"
    fail_comp_body = {
        "student_id": bob_id,
        "unit_id": UNIT,
        "files": {
            "schemas.py": (comp_base_dir / "schemas.py").read_text(encoding="utf-8"),
            "extractor.py": (comp_base_dir / "extractor.py").read_text(encoding="utf-8"),
        }
    }
    c_comp, r_comp = req("/practice/attempt", method="POST", body=fail_comp_body)
    check("bob completion attempt fails via HTTP 200", c_comp == 200 and r_comp.get("passed") is False)

    code, bob_route3 = req(f"/practice/route?student_id={bob_id}&unit={UNIT}")
    check("bob route after failed completion is scaffold_active", bob_route3.get("status") == "scaffold_active")
    check("bob scaffold is active", bob_route3.get("scaffold_active") is True)
    check("bob recommended step is worked_example", bob_route3.get("recommended_step") == "worked_example")

    comp_callout = bob_route3.get("scaffold_callout")
    check("scaffold callout is completion_retry", comp_callout.get("type") == "completion_retry")
    check("scaffold callout targets extractor.py", comp_callout.get("target_file") == "extractor.py")
    check("scaffold callout anchor is worked-example", comp_callout.get("anchor") == "worked-example")

    bob_steps3 = {s["id"]: s for s in bob_route3.get("steps", [])}
    check("bob worked example step is scaffold", bob_steps3.get("worked_example", {}).get("status") == "scaffold")
    check("bob completion step is retry", bob_steps3.get("completion", {}).get("status") == "retry")

    print("\n== 6. completion pass: route complete ==")
    # Alice passes completion problem with worked example solution
    we_dir = REPO_ROOT / "content" / "units" / "phase-3" / "3.2.1" / "worked-example"
    pass_comp_body = {
        "student_id": alice_id,
        "unit_id": UNIT,
        "files": {
            "schemas.py": (we_dir / "schemas.py").read_text(encoding="utf-8"),
            "extractor.py": (we_dir / "extractor.py").read_text(encoding="utf-8"),
        }
    }
    c_comp_pass, r_comp_pass = req("/practice/attempt", method="POST", body=pass_comp_body)
    check("alice completion attempt passes via HTTP 200", c_comp_pass == 200 and r_comp_pass.get("passed") is True)

    code, alice_route2 = req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
    check("alice route after completion pass is completed", alice_route2.get("status") == "completed")
    check("alice recommended step is build", alice_route2.get("recommended_step") == "build")
    check("alice scaffold is not active", alice_route2.get("scaffold_active") is False)

    alice_steps2 = {s["id"]: s for s in alice_route2.get("steps", [])}
    check("alice all steps completed or optional", all(s["status"] in ("done", "optional") for s in alice_steps2.values()))
    check("alice completion step is done", alice_steps2.get("completion", {}).get("status") == "done")

    print("\n== 7. S3.3 due-ness intentionally does not alter routing ==")
    # Advance clock to T+3d, T+7d, T+10d where seeds become due for spaced re-checks
    set_now("2026-03-04T09:00:00+00:00")  # T+3d
    # Check spaced schedule reports due seeds
    sched_code, sched = req(f"/practice/retrieval/schedule?student_id={alice_id}&unit={UNIT}")
    check("spaced schedule reports due seeds at T+3d", sched.get("due_count", 0) > 0)

    # Assert alice route is STILL completed and NOT reverted to drills
    code, alice_route_t3 = req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
    check("alice route is still completed at T+3d despite due seeds", alice_route_t3.get("status") == "completed")
    check("alice recommended step is still build at T+3d", alice_route_t3.get("recommended_step") == "build")

    set_now("2026-03-11T09:00:00+00:00")  # T+10d
    code, alice_route_t10 = req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
    check("alice route is still completed at T+10d", alice_route_t10.get("status") == "completed")

    print("\n== 8. unenrolled student: honest empty state ==")
    code, carol_route = req(f"/practice/route?student_id={carol_id}&unit={UNIT}")
    check("carol route returns HTTP 200", code == 200)
    check("carol enrolled is False", carol_route.get("enrolled") is False)
    check("carol status is unenrolled", carol_route.get("status") == "unenrolled")
    check("carol recommended step is null", carol_route.get("recommended_step") is None)
    check("carol steps list is empty", carol_route.get("steps") == [])

    print("\n== 9. no routing rules file: loud refusal, never silent default ==")
    # Request route for a unit without a routing rules file
    code_bad, resp_bad = req(f"/practice/route?student_id={alice_id}&unit=9.9.9")
    check("missing routing rules file returns HTTP 404", code_bad == 404)
    check("error is routing_rules_not_found", resp_bad.get("error") == "routing_rules_not_found", str(resp_bad))

    print("\n== 10. validator negative probes ==")
    # Run validate-routing.py against positive content
    proc_val = subprocess.run([sys.executable, str(VALIDATE_ROUTING)], capture_output=True, text=True)
    check("validate-routing.py passes on valid content", proc_val.returncode == 0)

    # Plant invalid routing rule in a scratch temp dir
    with tempfile.TemporaryDirectory(prefix="keel-scratch-val-") as scratch_dir:
        scratch_content = Path(scratch_dir) / "content"
        shutil.copytree(REPO_ROOT / "content", scratch_content)
        (scratch_content / "routing" / "bad-name.yaml").write_text("unit_id: 'bad'\n", encoding="utf-8")
        proc_bad = subprocess.run(
            [sys.executable, str(scratch_content / "tools" / "validate-routing.py")],
            cwd=str(scratch_content.parent),
            capture_output=True,
            text=True,
        )
        check("validate-routing.py rejects bad filename stem with exit 1", proc_bad.returncode == 1)
        check("validator names the offending file", "bad-name.yaml" in proc_bad.stdout or "bad-name.yaml" in proc_bad.stderr)

    print("\n== 11. gate/rebate/unlock isolation ==")
    env = os.environ.copy()
    env["KEEL_GATE_ONCE"] = "1"
    env["KEEL_REBATE_ONCE"] = "1"
    subprocess.run([sys.executable, str(ENGINE)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(MACHINE)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    unlocked_alice = db_sql("SELECT count(*) FROM unlocked_units WHERE student_id = %d;" % alice_id)
    check("alice has 0 unlocked units from practice", unlocked_alice[0][0] in ("0", 0))
    rebates_alice = db_sql("SELECT count(*) FROM rebates WHERE student_id = %d AND status = 'earned';" % alice_id)
    check("alice has 0 earned rebates from practice", rebates_alice[0][0] in ("0", 0))

    print("\n== 12. pure read path: zero new rows anywhere ==")
    before_counts = get_db_counts()
    for _ in range(5):
        req(f"/practice/route?student_id={alice_id}&unit={UNIT}")
        req(f"/practice/route?student_id={bob_id}&unit={UNIT}")
        req(f"/practice/route?student_id={carol_id}&unit={UNIT}")
    after_counts = get_db_counts()
    check("pure read path: database table counts 100% identical before and after route queries", before_counts == after_counts, f"{before_counts} vs {after_counts}")

    print(f"\n== Summary: {PASS_COUNT} passed, {FAIL_COUNT} failed ==")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
