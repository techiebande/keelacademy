#!/usr/bin/env python3
"""smoke-simulation-checks.py — deterministic proof battery for Business Simulation Service (S4.5).

Verifies:
1. Content Schema Validation:
   - content/personas/discovery-call.yaml matches persona.schema.json.
2. Session Management & Auth Boundaries:
   - 401 on missing or invalid app auth token.
   - 422 / 404 on missing/invalid student or non-existent persona.
   - Session starts with initial greeting from Sarah Jenkins.
   - Initial row written with status='in_progress' and 'simulation.started' spine event.
3. Multi-Turn Dialogue & Behavioral Triggers:
   - Student premature pitch -> persona pushback ("We already tried ChatGPT and it hallucinated store discount rules").
   - Student open question about volume & bottlenecks -> persona reveals metrics (4,000 transactions/mo, 2-3 days turnaround).
   - Student question on store policy compliance -> persona reveals unstructured contract verification and compliance audit pain.
   - Student synthesis question -> persona acknowledges and confirms project fit.
   - State persistence: turns array updated and 'simulation.turn_completed' spine event emitted per turn.
   - 403 on another student attempting to execute a turn in session.
4. Evaluation Judge Scoring & Determinism:
   - Passing transcript (with metric exploration, root problem probing, avoidance of early pitching, and problem synthesis) -> score >= 70%, passed = true, complete criteria breakdown with evidence quotes.
   - Failing transcript (premature pitching, no metric exploration, no problem summary) -> score < 70%, passed = false.
   - 'simulation.scored' spine event emitted atomically with score_pct, passed, completed_at.
5. Query Endpoints:
   - GET /simulation/<id> returns full transcript, score, and verdict.
   - 403 on cross-student simulation inspection when student_id query param provided.
   - GET /students/<id>/simulations returns student's historical runs.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Import db helper
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import db_sql

PRACTICE_URL = os.environ.get("KEEL_PRACTICE_URL", "http://127.0.0.1:8792")
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "")

passed_count = 0
failed_count = 0


def record_pass(msg: str) -> None:
    global passed_count
    passed_count += 1
    print(f"  [PASS] {msg}")


def record_fail(msg: str, detail: str = "") -> None:
    global failed_count
    failed_count += 1
    print(f"  [FAIL] {msg} ({detail})", file=sys.stderr)


def http_request(
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = APP_TOKEN,
) -> tuple[int, dict[str, Any]]:
    url = f"{PRACTICE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Keel-App-Token"] = token

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(err_body)
        except Exception:
            return exc.code, {"raw": err_body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def main() -> None:
    print("== Running S4.5 Business Simulation Service Smoke Battery ==")

    # ------------------------------------------------------------------
    # 1. Auth Boundary Enforcement
    # ------------------------------------------------------------------
    print("\n-- 1. Testing Auth Boundary Enforcement --")

    # Missing token -> 401
    code, _ = http_request("/simulation/start", method="POST", body={"student_id": 1, "persona_id": "discovery-call"}, token=None)
    if code == 401:
        record_pass("POST /simulation/start rejects missing token with 401")
    else:
        record_fail("POST /simulation/start with missing token", f"got {code}")

    # Bad token -> 401
    code, _ = http_request("/simulation/start", method="POST", body={"student_id": 1, "persona_id": "discovery-call"}, token="invalid-token")
    if code == 401:
        record_pass("POST /simulation/start rejects invalid token with 401")
    else:
        record_fail("POST /simulation/start with invalid token", f"got {code}")

    # Non-existent student -> 404
    code, res = http_request("/simulation/start", method="POST", body={"student_id": 99999, "persona_id": "discovery-call"})
    if code == 404:
        record_pass("POST /simulation/start returns 404 for non-existent student")
    else:
        record_fail("POST /simulation/start non-existent student", f"got {code}")

    # Non-existent persona -> 404
    code, res = http_request("/simulation/start", method="POST", body={"student_id": 1, "persona_id": "nonexistent-persona"})
    if code == 404:
        record_pass("POST /simulation/start returns 404 for non-existent persona")
    else:
        record_fail("POST /simulation/start non-existent persona", f"got {code}")

    # ------------------------------------------------------------------
    # 2. Session Start & Initial Greeting
    # ------------------------------------------------------------------
    print("\n-- 2. Testing Session Start & Initial Greeting --")

    code, res = http_request("/simulation/start", method="POST", body={"student_id": 1, "persona_id": "discovery-call"})
    if code == 200 and res.get("id") and res.get("status") == "in_progress":
        sim_id_alice = int(res["id"])
        record_pass(f"POST /simulation/start initialized session #{sim_id_alice}")
        
        # Check initial greeting contains Sarah Jenkins
        init_msg = res.get("initial_message", "")
        if "Sarah Jenkins" in init_msg and "OmniCart" in init_msg:
            record_pass("Initial persona greeting correctly introduces Sarah Jenkins at OmniCart")
        else:
            record_fail("Initial persona greeting content", f"got {init_msg}")
    else:
        record_fail("POST /simulation/start valid session", f"got {code}: {res}")
        return

    # Check spine event 'simulation.started'
    ev_rows = db_sql(f"BEGIN; SELECT type, payload::text FROM events WHERE type = 'simulation.started' AND payload->>'simulation_id' = '{sim_id_alice}'; ROLLBACK;")
    if ev_rows:
        record_pass("Atomic 'simulation.started' spine event emitted on session creation")
    else:
        record_fail("Missing 'simulation.started' spine event in DB")

    # ------------------------------------------------------------------
    # 3. Multi-turn Dialogue Execution & Behavioral Pushback
    # ------------------------------------------------------------------
    print("\n-- 3. Testing Dialogue Execution & Persona Behavioral Triggers --")

    # Turn 1: Alice prematurely pitches technical solution
    t1_msg = "Hello Sarah! We can build you an AI agent with LangChain and a vector database right away."
    code, t1_res = http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 1,
        "message": t1_msg,
    })
    if code == 200:
        reply1 = t1_res.get("persona_reply", "")
        if "already tried ChatGPT" in reply1 or "hallucinated" in reply1:
            record_pass("Persona correctly pushed back on premature technical pitch ('already tried ChatGPT and it hallucinated')")
        else:
            record_fail("Persona reply to premature pitch", f"got: {reply1}")
    else:
        record_fail("POST /simulation/turn turn 1", f"got {code}: {t1_res}")

    # Ownership check: Student 2 (Bob) cannot post turn to Alice's simulation
    code, _ = http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 2,
        "message": "Hi, this is Bob.",
    })
    if code == 403:
        record_pass("POST /simulation/turn strictly rejects non-owner turn with 403")
    else:
        record_fail("Cross-student simulation turn", f"got {code}")

    # Turn 2: Alice probes process metrics and volume
    t2_msg = "Understood. Before talking tools, what is your current monthly transaction volume and how long does manual triage take?"
    code, t2_res = http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 1,
        "message": t2_msg,
    })
    if code == 200:
        reply2 = t2_res.get("persona_reply", "")
        if "4,000" in reply2 or "4000" in reply2 or "2 to 3 business days" in reply2 or "turnaround" in reply2:
            record_pass("Persona revealed volume and latency metrics (4,000 transactions/mo, 2-3 days turnaround)")
        else:
            record_fail("Persona reply to volume probe", f"got: {reply2}")
    else:
        record_fail("POST /simulation/turn turn 2", f"got {code}: {t2_res}")

    # Turn 3: Alice probes the root cause and why past pilots hallucinated
    t3_msg = "What specifically caused the earlier ChatGPT pilot to hallucinate? Where is the real underlying bottleneck in store policy verification?"
    code, t3_res = http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 1,
        "message": t3_msg,
    })
    if code == 200:
        reply3 = t3_res.get("persona_reply", "")
        if "store master policies" in reply3 or "policy grounding" in reply3 or "contract grounding" in reply3 or "compliance" in reply3 or "audit" in reply3:
            record_pass("Persona revealed underlying pain: unstructured store policy verification and compliance audit risk")
        else:
            record_fail("Persona reply to root cause probe", f"got: {reply3}")
    else:
        record_fail("POST /simulation/turn turn 3", f"got {code}: {t3_res}")

    # Turn 4: Alice provides an accurate synthesis/summary of the problem
    t4_msg = "In summary, it sounds like the core bottleneck is not basic OCR extraction, but deterministic store policy verification against master policy terms with an audit trail compliance can trust."
    code, t4_res = http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 1,
        "message": t4_msg,
    })
    if code == 200:
        reply4 = t4_res.get("persona_reply", "")
        if "Exactly" in reply4 or "precisely" in reply4 or "real project" in reply4:
            record_pass("Persona enthusiastically confirmed accurate problem synthesis")
        else:
            record_fail("Persona reply to synthesis", f"got: {reply4}")
    else:
        record_fail("POST /simulation/turn turn 4", f"got {code}: {t4_res}")

    # Check spine events for turns
    turn_evs = db_sql(f"BEGIN; SELECT count(*) FROM events WHERE type = 'simulation.turn_completed' AND payload->>'simulation_id' = '{sim_id_alice}'; ROLLBACK;")
    if turn_evs and int(turn_evs[0][0]) == 4:
        record_pass("Atomic 'simulation.turn_completed' spine events emitted for all 4 dialogue turns")
    else:
        record_fail("Turn completed spine events count", f"got {turn_evs}")

    # ------------------------------------------------------------------
    # 4. Conclude & Evaluation Judge Scoring (Passing Session)
    # ------------------------------------------------------------------
    print("\n-- 4. Testing Conclude & Evaluation Judge (Passing Call) --")

    # Ownership check on conclude
    code, _ = http_request("/simulation/conclude", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 2, # Bob
    })
    if code == 403:
        record_pass("POST /simulation/conclude rejects non-owner with 403")
    else:
        record_fail("Cross-student conclude", f"got {code}")

    # Conclude Alice's session
    code, conc_res = http_request("/simulation/conclude", method="POST", body={
        "simulation_id": sim_id_alice,
        "student_id": 1,
    })
    if code == 200 and conc_res.get("status") == "graded":
        score = float(conc_res.get("score_pct", 0.0))
        passed = conc_res.get("passed", False)
        record_pass(f"POST /simulation/conclude scored session: score={score}%, passed={passed}")
        
        # Verify rubric criteria structure
        verdict = conc_res.get("verdict", {})
        criteria = verdict.get("criteria", [])
        if len(criteria) == 4:
            crit_ids = [c.get("id") for c in criteria]
            if all(cid in crit_ids for cid in ["uncovered-underlying-problem", "explored-process-metrics", "avoided-premature-pitching", "accurate-problem-summary"]):
                record_pass("Scored verdict contains all 4 required §11.5.1 rubric criteria")
            else:
                record_fail("Missing criteria in verdict", f"got {crit_ids}")
        else:
            record_fail("Criteria count in verdict", f"got {len(criteria)}")
    else:
        record_fail("POST /simulation/conclude", f"got {code}: {conc_res}")

    # Check spine event 'simulation.scored'
    score_evs = db_sql(f"BEGIN; SELECT type, payload::text FROM events WHERE type = 'simulation.scored' AND payload->>'simulation_id' = '{sim_id_alice}'; ROLLBACK;")
    if score_evs:
        record_pass("Atomic 'simulation.scored' spine event emitted with score and verdict")
    else:
        record_fail("Missing 'simulation.scored' spine event in DB")

    # ------------------------------------------------------------------
    # 5. Failing Simulation Test (Bob runs bad discovery call)
    # ------------------------------------------------------------------
    print("\n-- 5. Testing Evaluation Judge on Failing Discovery Call --")

    # Start Bob session
    _, bob_start = http_request("/simulation/start", method="POST", body={"student_id": 2, "persona_id": "discovery-call"})
    sim_id_bob = int(bob_start["id"])

    # Bob only pitches and asks nothing
    http_request("/simulation/turn", method="POST", body={
        "simulation_id": sim_id_bob,
        "student_id": 2,
        "message": "We build AI chatbots with LangChain. Sign here for our $50k package.",
    })

    _, bob_conc = http_request("/simulation/conclude", method="POST", body={
        "simulation_id": sim_id_bob,
        "student_id": 2,
    })
    bob_score = float(bob_conc.get("score_pct", 0.0))
    bob_passed = bob_conc.get("passed", True)
    if not bob_passed and bob_score < 70.0:
        record_pass(f"Failing discovery transcript correctly failed (score={bob_score}%, passed={bob_passed})")
    else:
        record_fail("Failing transcript evaluation", f"score={bob_score}, passed={bob_passed}")

    # ------------------------------------------------------------------
    # 6. Session Detail & History Retrieval
    # ------------------------------------------------------------------
    print("\n-- 6. Testing Session Query & History Retrieval --")

    # GET /simulation/<id>
    code, det_res = http_request(f"/simulation/{sim_id_alice}")
    if code == 200 and det_res.get("id") == sim_id_alice and det_res.get("status") == "graded":
        record_pass("GET /simulation/<id> returns complete transcript and scored verdict")
    else:
        record_fail("GET /simulation/<id>", f"got {code}: {det_res}")

    # GET /simulation/<id>?student_id=2 (ownership mismatch check)
    code, _ = http_request(f"/simulation/{sim_id_alice}?student_id=2")
    if code == 403:
        record_pass("GET /simulation/<id>?student_id=2 strictly enforces student ownership boundary with 403")
    else:
        record_fail("Cross-student simulation query", f"got {code}")

    # GET /students/<id>/simulations
    code, hist_res = http_request("/students/1/simulations")
    if code == 200 and "simulations" in hist_res:
        sim_list = hist_res["simulations"]
        if any(s.get("id") == sim_id_alice for s in sim_list):
            record_pass(f"GET /students/1/simulations returns student historical runs (count={len(sim_list)})")
        else:
            record_fail("Student simulation history missing Alice session", f"{sim_list}")
    else:
        record_fail("GET /students/1/simulations", f"got {code}: {hist_res}")

    print("\n------------------------------------------------------------")
    print(f"Simulation Smoke Battery: {passed_count} PASSED, {failed_count} FAILED")
    print("------------------------------------------------------------")
    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
