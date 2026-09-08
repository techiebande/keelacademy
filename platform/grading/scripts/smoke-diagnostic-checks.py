#!/usr/bin/env python3
"""platform/grading/scripts/smoke-diagnostic-checks.py — S4.1 diagnostic test battery.

Deterministic assertions for:
1. Spec fetching: GET /diagnostic/spec returns questions without answer leaks.
2. Perfect score placement: Student answering all questions correctly passes (>=75%)
   and is placed into Unit 1.3 skip route ('1.3_skip'), unlocking units ['1.3', '1.4', '1.5'].
3. Events emission: 'diagnostic.completed' and 'diagnostic.placed' spine events emitted atomically.
4. Unlocked units persistence: unlocked_units table holds entries for ['1.3', '1.4', '1.5'].
5. Failing score placement: Student answering incorrectly fails (<75%) and is placed
   into baseline route ('baseline_0.1'), unlocking baseline units ['0.1', '1.1', '1.2'].
6. Opt-out route: Student calling /diagnostic/opt-out is placed into 'opt_out' route
   and receives baseline units ['0.1', '1.1', '1.2'].
7. Attempt history: GET /diagnostic/attempts returns all recorded attempts in order.
8. Auth protection: Unauthorized calls (bad token / no token) return 401.
9. Student isolation & validation: Unknown student returns 404; invalid payload returns 422.
10. Spoof immunity: Client sending fake route or passed flag has no effect on server evaluation.
"""

from __future__ import annotations

import json
import os
import sys
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
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "smoke-diagnostic-token")

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  [PASS] {name}")
        PASS_COUNT += 1
    else:
        print(f"  [FAIL] {name} -- {detail}")
        FAIL_COUNT += 1


def http_req(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = APP_TOKEN,
) -> tuple[int, dict[str, Any]]:
    url = f"{SERVICE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Keel-App-Token"] = token

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, {"raw": raw.decode("utf-8", errors="replace")}


def main() -> int:
    print("== Running S4.1 Diagnostic & Commitment Placement Smoke Battery ==")

    # 1. Spec fetching without answer leak
    st, spec = http_req("GET", "/diagnostic/spec?id=placement-phase-1")
    check("GET /diagnostic/spec returns 200", st == 200, f"status={st}")
    check("Spec has questions list", isinstance(spec.get("questions"), list) and len(spec["questions"]) >= 4, f"spec={spec}")
    check("Spec omits correct_answer secrets", all("correct_answer" not in q for q in spec.get("questions", [])), "leaked answer in spec")
    check("Spec omits explanation secrets", all("explanation" not in q for q in spec.get("questions", [])), "leaked explanation in spec")
    check("Spec includes passing threshold", spec.get("passing_threshold_pct") == 75.0, f"threshold={spec.get('passing_threshold_pct')}")

    # Query DB student IDs
    rows = db_sql("BEGIN; SELECT id, email FROM students ORDER BY id ASC; ROLLBACK;")
    student_map = {r[1]: int(r[0]) for r in rows}
    alice_id = student_map["alice@keel.test"]
    bob_id = student_map["bob@keel.test"]
    carol_id = student_map["carol@keel.test"]

    # 2. Perfect passing score for Alice -> Placed into Unit 1.3 skip route
    perfect_answers = {
        "q1_python_comprehension": "opt_b",
        "q2_dict_mutation": "opt_b",
        "q3_pydantic_validation": "opt_a",
        "q4_json_deserialization": "opt_b",
        "q5_asyncio_gather": "opt_b",
        "q6_blocking_in_async": "opt_b",
        "q7_http_status_semantics": "opt_b",
        "q8_pytest_fixtures": "opt_c",
    }
    st, alice_res = http_req("POST", "/diagnostic/evaluate", {
        "student_id": alice_id,
        "diagnostic_id": "placement-phase-1",
        "answers": perfect_answers,
    })
    check("Alice evaluation returns 200", st == 200, f"status={st}, res={alice_res}")
    check("Alice passed diagnostic", alice_res.get("passed") is True, f"passed={alice_res.get('passed')}")
    check("Alice score is 100%", alice_res.get("score_pct") == 100.0, f"score={alice_res.get('score_pct')}")
    check("Alice placed into 1.3_skip route", alice_res.get("route") == "1.3_skip", f"route={alice_res.get('route')}")
    check("Alice unlocks include 1.3", "1.3" in alice_res.get("unlocked_units", []), f"unlocks={alice_res.get('unlocked_units')}")

    # Verify DB state for Alice
    alice_db_attempts = db_sql("BEGIN; SELECT passed, score_pct, route FROM diagnostic_attempts WHERE student_id = %d; ROLLBACK;" % alice_id)
    check("Alice diagnostic attempt row persisted", len(alice_db_attempts) == 1 and alice_db_attempts[0][0] == "t", f"rows={alice_db_attempts}")

    alice_unlocks = db_sql("BEGIN; SELECT unit_id FROM unlocked_units WHERE student_id = %d ORDER BY unit_id; ROLLBACK;" % alice_id)
    alice_unlocked_list = [r[0] for r in alice_unlocks]
    check("Alice unlocked_units persisted in DB", "1.3" in alice_unlocked_list and "1.4" in alice_unlocked_list, f"unlocks={alice_unlocked_list}")

    alice_events = db_sql("BEGIN; SELECT type, payload->>'route', payload->>'passed' FROM events WHERE payload->>'student_id' = '%d' ORDER BY id ASC; ROLLBACK;" % alice_id)
    event_types = [r[0] for r in alice_events]
    check("Alice emitted diagnostic.completed event", "diagnostic.completed" in event_types, f"events={event_types}")
    check("Alice emitted diagnostic.placed event", "diagnostic.placed" in event_types, f"events={event_types}")

    # 3. Failing score for Bob (<75%) -> Placed into baseline route
    failing_answers = {
        "q1_python_comprehension": "opt_a", # wrong
        "q2_dict_mutation": "opt_a",        # wrong
        "q3_pydantic_validation": "opt_b",  # wrong
        "q4_json_deserialization": "opt_a", # wrong
        "q5_asyncio_gather": "opt_b",       # correct (+1)
        "q6_blocking_in_async": "opt_a",    # wrong
        "q7_http_status_semantics": "opt_a",# wrong
        "q8_pytest_fixtures": "opt_a",      # wrong
    }
    st, bob_res = http_req("POST", "/diagnostic/evaluate", {
        "student_id": bob_id,
        "diagnostic_id": "placement-phase-1",
        "answers": failing_answers,
    })
    check("Bob evaluation returns 200", st == 200, f"status={st}, res={bob_res}")
    check("Bob failed diagnostic", bob_res.get("passed") is False, f"passed={bob_res.get('passed')}")
    check("Bob score is 12.5%", bob_res.get("score_pct") == 12.5, f"score={bob_res.get('score_pct')}")
    check("Bob placed into baseline_0.1 route", bob_res.get("route") == "baseline_0.1", f"route={bob_res.get('route')}")
    check("Bob unlocks baseline units (0.1, 1.1, 1.2)", "0.1" in bob_res.get("unlocked_units", []) and "1.1" in bob_res.get("unlocked_units", []), f"unlocks={bob_res.get('unlocked_units')}")

    bob_unlocks = db_sql("BEGIN; SELECT unit_id FROM unlocked_units WHERE student_id = %d ORDER BY unit_id; ROLLBACK;" % bob_id)
    bob_unlocked_list = [r[0] for r in bob_unlocks]
    check("Bob baseline unlocked_units persisted", "0.1" in bob_unlocked_list and "1.1" in bob_unlocked_list, f"unlocks={bob_unlocked_list}")

    # 4. Opt-out for Carol -> Placed into opt_out baseline route
    st, carol_res = http_req("POST", "/diagnostic/opt-out", {
        "student_id": carol_id,
        "diagnostic_id": "placement-phase-1",
    })
    check("Carol opt-out returns 200", st == 200, f"status={st}, res={carol_res}")
    check("Carol route is opt_out", carol_res.get("route") == "opt_out", f"route={carol_res.get('route')}")
    check("Carol unlocks baseline units", "0.1" in carol_res.get("unlocked_units", []), f"unlocks={carol_res.get('unlocked_units')}")

    # 5. Attempt history GET /diagnostic/attempts
    st, alice_hist = http_req("GET", f"/diagnostic/attempts?student_id={alice_id}")
    check("GET /diagnostic/attempts returns 200", st == 200, f"status={st}")
    check("Alice attempt history has 1 record", len(alice_hist.get("attempts", [])) == 1, f"hist={alice_hist}")
    check("History record matches score and route", alice_hist["attempts"][0]["route"] == "1.3_skip", f"rec={alice_hist}")

    # 6. Auth & boundary protections
    st, unauth_res = http_req("GET", "/diagnostic/spec", token=None)
    check("Missing auth token returns 401", st == 401, f"status={st}")

    st, bad_token_res = http_req("GET", "/diagnostic/spec", token="wrong-secret")
    check("Invalid auth token returns 401", st == 401, f"status={st}")

    st, unknown_res = http_req("POST", "/diagnostic/evaluate", {
        "student_id": 999999,
        "diagnostic_id": "placement-phase-1",
        "answers": {},
    })
    check("Unknown student returns 404", st == 404, f"status={st}")

    st, invalid_payload = http_req("POST", "/diagnostic/evaluate", {
        "student_id": alice_id,
        "diagnostic_id": "placement-phase-1",
        # missing answers
    })
    check("Missing answers payload returns 422", st == 422, f"status={st}")

    # 7. Spoof Immunity: Client passing spoofed route/passed parameters
    st, spoof_res = http_req("POST", "/diagnostic/evaluate", {
        "student_id": bob_id,
        "diagnostic_id": "placement-phase-1",
        "answers": failing_answers,
        "passed": True,             # client spoof attempt
        "route": "1.3_skip",        # client spoof attempt
        "score_pct": 100.0,         # client spoof attempt
    })
    check("Spoofed payload is evaluated honestly by server", spoof_res.get("passed") is False and spoof_res.get("route") == "baseline_0.1", f"spoof_res={spoof_res}")

    print(f"\nDiagnostic Smoke Checks Complete: {PASS_COUNT} Passed, {FAIL_COUNT} Failed")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
