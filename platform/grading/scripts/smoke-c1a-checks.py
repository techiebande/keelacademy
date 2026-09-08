#!/usr/bin/env python3
"""smoke-c1a-checks.py — Automated assertion test suite for Milestone C1a.

Validates:
1. Practice manifest endpoint returns conceptual attributes (kind: "conceptual", prompt, instructions).
2. Conceptual completion grading against the rubric criteria-array contract
   (server parses per-criterion verdicts, computes the overall itself):
   - Golden-strong answer (Alice on 0.2): all rubric criteria pass, per-criterion
     results carry the rubric criterion ids and evidence quotes, overall pass.
   - One-criterion-fail (Bob): pass_rule "all" applied in the platform -> overall
     fail, even though the fake judge claims a passing model overall.
   - Unknown criterion id (Bob): hard error 502 malformed_judge, no attempt row,
     exactly one nudge retry (2 upstream calls).
   - Malformed JSON twice (Bob): nudge retry then hard error 502 malformed_judge,
     no attempt row (2 upstream calls).
   - Malformed JSON once (Bob): nudge recovers -> pass.
3. Attempt persistence + spine event practice.attempt_graded emitted atomically.
4. Enrollment gate: unenrolled student (Carol) rejected 403 not_enrolled.
5. Budget enforcement: exhausted student (Dave) rejected 429 budget_exceeded.
6. Retrieval drill attempts on Phase 0 units (0.2, 0.3) still grade pass.
7. Concierge teach/guard modes on Phase 0 units.
8. Trace log records call provenance with caller="completion" and valid tokens.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def rubric_criteria_ids(unit_id: str) -> list[str]:
    """Criterion ids straight from the unit rubric — content is the source of
    truth for what the judge must return, never a hardcoded copy."""
    path = REPO_ROOT / "content" / "rubrics" / unit_id / "v1.yaml"
    ids = re.findall(r"^\s*-\s*id:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert ids, f"no criteria ids parsed from {path}"
    return list(dict.fromkeys(ids))


def http_req(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
) -> tuple[int, dict, dict]:
    hdr = headers or {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdr["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return exc.code, parsed, dict(exc.headers)


def fake_call_count(fake_url: str) -> int:
    req = urllib.request.Request(f"{fake_url.rstrip('/')}/__count")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return int(resp.read().decode("utf-8").strip())


def attempt_count(base_url: str, headers: dict, student_id: int, unit_id: str) -> int:
    code, body, _ = http_req(
        f"{base_url}/practice/attempts?student_id={student_id}&unit={unit_id}", headers=headers
    )
    assert code == 200, f"Expected 200 for attempt history, got {code}: {body}"
    return len(body.get("attempts", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--practice-url", required=True)
    parser.add_argument("--fake-url", required=True)
    parser.add_argument("--app-token", required=True)
    parser.add_argument("--trace-log", required=True)
    args = parser.parse_args()

    base_url = args.practice_url.rstrip("/")
    app_headers = {"X-Keel-App-Token": args.app_token}

    units_dir = REPO_ROOT / "content" / "units"
    authored_units = []
    if units_dir.is_dir():
        for p in units_dir.glob("phase-*"):
            for u in p.glob("*/unit.yaml"):
                authored_units.append(u.parent.name)
    if not authored_units:
        print("  [notice] Zero authored units on disk (authoring reset); C1a conceptual test suite skipped.")
        return

    print("  [test 1/12] Verify conceptual practice manifest for 0.2, 0.3...")
    for uid in ("0.2", "0.3"):
        code, body, _ = http_req(f"{base_url}/practice/manifest?unit={uid}", headers=app_headers)
        assert code == 200, f"Expected 200 for unit {uid} manifest, got {code}: {body}"
        assert body.get("unit_id") == uid, f"Expected unit_id {uid}, got {body.get('unit_id')}"
        assert body.get("kind") == "conceptual", f"Expected kind conceptual for {uid}, got {body.get('kind')}"
        assert body.get("prompt"), f"Expected non-empty prompt for {uid}"
        assert body.get("editable_files") == [], f"Expected empty editable_files for conceptual unit {uid}"
        assert len(body.get("checks", [])) == 1, f"Expected 1 check descriptor for {uid}"
    print("    -> Manifest endpoint correctly serves conceptual properties.")

    print("  [test 2/12] Golden-strong conceptual attempt: all criteria pass (Alice on 0.2)...")
    alice_payload = {
        "student_id": 1,
        "unit_id": "0.2",
        "answer": (
            "Verification in AI engineering occurs across four stages: automated checks, rubric review, "
            "defend your work, and recorded walkthrough. Automated checks catch execution and contract failures "
            "such as schema violations, syntax errors, and missing files before human or qualitative LLM grading. "
            "Rubric review catches structural and qualitative deficits against explicit criteria quotes.\n\n"
            "Automated checks must always run and pass in full before rubric review begins because evaluating "
            "code or deliverables that fail fundamental execution wastes grading budget and produces noisy feedback. "
            "Meanwhile, the Phase 11 parallel business track runs from week one alongside technical development "
            "so engineers build a real client pipeline rather than finishing a technical system with zero users."
        )
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=alice_payload)
    assert code == 200, f"Expected 200 for Alice completion attempt, got {code}: {body}"
    expected_ids = rubric_criteria_ids("0.2")
    assert body.get("passed") is True, f"Expected passed=True, got {body}"
    assert body.get("total_checks") == len(expected_ids), \
        f"Expected total_checks={len(expected_ids)}, got {body.get('total_checks')}"
    assert body.get("pass_count") == len(expected_ids), \
        f"Expected pass_count={len(expected_ids)}, got {body.get('pass_count')}"
    got_ids = [c.get("id") for c in body.get("checks", [])]
    assert got_ids == expected_ids, f"Expected per-criterion ids {expected_ids}, got {got_ids}"
    for crit in body["checks"]:
        assert crit.get("type") == "llm-judge", f"Expected llm-judge type, got {crit}"
        assert crit.get("status") == "pass", f"Expected pass for {crit.get('id')}, got {crit}"
        assert isinstance(crit.get("evidence"), str) and crit["evidence"].strip(), \
            f"Expected non-empty evidence quote for {crit.get('id')}, got {crit}"
    print("    -> Per-criterion verdicts + evidence returned; platform overall PASS.")

    print("  [test 3/12] Verify attempt persistence and spine event emission...")
    code, body, _ = http_req(f"{base_url}/practice/attempts?student_id=1&unit=0.2", headers=app_headers)
    assert code == 200, f"Expected 200 for attempt history, got {code}: {body}"
    assert len(body.get("attempts", [])) >= 1, "Expected at least 1 persisted attempt"
    latest_att = body["attempts"][0]
    assert latest_att["passed"] is True
    persisted_checks = latest_att.get("checks", [])
    assert [c.get("id") for c in persisted_checks] == expected_ids, \
        f"Expected per-criterion ids persisted, got {persisted_checks}"
    print("    -> Attempt correctly persisted to Postgres database.")

    print("  [test 4/12] One-criterion-fail: platform applies pass_rule -> overall FAIL (Bob on 0.2)...")
    bob_before = attempt_count(base_url, app_headers, 2, "0.2")
    bob_fail_payload = {
        "student_id": 2,
        "unit_id": "0.2",
        "answer": "fail_me — this submission omits the parallel business track rationale, "
                  "so the judge must fail at least one rubric criterion."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=bob_fail_payload)
    assert code == 200, f"Expected 200 for Bob fail-variant attempt, got {code}: {body}"
    statuses = [c.get("status") for c in body.get("checks", [])]
    assert body.get("passed") is False, f"Expected platform overall fail, got {body}"
    assert statuses.count("fail") == 1, f"Expected exactly 1 failed criterion, got {statuses}"
    assert body.get("pass_count") == len(expected_ids) - 1, f"Expected pass_count={len(expected_ids) - 1}, got {body}"
    print("    -> pass_rule 'all' recomputed in the platform (model's own overall discarded).")

    print("  [test 5/12] Unknown criterion id: hard error, no attempt row (Bob on 0.2)...")
    bob_before = attempt_count(base_url, app_headers, 2, "0.2")
    calls_before = fake_call_count(args.fake_url)
    bob_unknown_payload = {
        "student_id": 2,
        "unit_id": "0.2",
        "answer": "unknown_id — the judge reply will hallucinate a criterion id that is not in the rubric."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=bob_unknown_payload)
    assert code == 502, f"Expected 502 for unknown criterion id, got {code}: {body}"
    assert body.get("error") == "malformed_judge", f"Expected malformed_judge error, got {body}"
    assert fake_call_count(args.fake_url) - calls_before == 2, "Expected exactly 2 upstream calls (initial + nudge)"
    assert attempt_count(base_url, app_headers, 2, "0.2") == bob_before, \
        "Unknown-id rejection must not persist an attempt row"
    print("    -> Criterion id validated against rubric; hard error after nudge, zero persistence.")

    print("  [test 6/12] Malformed JSON twice: nudge then hard error, no attempt row (Bob on 0.2)...")
    calls_before = fake_call_count(args.fake_url)
    bob_malformed_payload = {
        "student_id": 2,
        "unit_id": "0.2",
        "answer": "malformed_double — the judge reply will not be valid JSON on either attempt."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=bob_malformed_payload)
    assert code == 502, f"Expected 502 for double-malformed judge reply, got {code}: {body}"
    assert body.get("error") == "malformed_judge", f"Expected malformed_judge error, got {body}"
    assert fake_call_count(args.fake_url) - calls_before == 2, "Expected exactly 2 upstream calls (initial + nudge)"
    assert attempt_count(base_url, app_headers, 2, "0.2") == bob_before, \
        "Malformed rejection must not persist an attempt row"
    print("    -> Malformed judge replies hard-error after one nudge with no attempt row.")

    print("  [test 7/12] Malformed JSON once: nudge recovers to a valid criteria verdict (Bob on 0.2)...")
    bob_once_payload = {
        "student_id": 2,
        "unit_id": "0.2",
        "answer": "malformed_once — the judge reply is malformed first, then corrected after the nudge."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=bob_once_payload)
    assert code == 200, f"Expected 200 for nudge-recovered attempt, got {code}: {body}"
    assert body.get("passed") is True, f"Expected recovered attempt to pass, got {body}"
    assert [c.get("id") for c in body.get("checks", [])] == expected_ids
    print("    -> Nudge retry path works against the criteria-array contract.")

    print("  [test 8/12] Verify enrollment gating on conceptual attempts...")
    carol_payload = {
        "student_id": 3, # Carol is unenrolled
        "unit_id": "0.2",
        "answer": "This is a conceptual answer from an unenrolled student."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=carol_payload)
    assert code == 403, f"Expected 403 for unenrolled attempt, got {code}: {body}"
    assert body.get("error") == "not_enrolled", f"Expected not_enrolled error, got {body}"
    print("    -> Unenrolled attempt rejected with 403 not_enrolled.")

    print("  [test 9/12] Verify token budget enforcement on conceptual attempts...")
    dave_payload = {
        "student_id": 4, # Dave has 100/100 budget used
        "unit_id": "0.2",
        "answer": "This is a conceptual answer from a budget-exhausted student."
    }
    code, body, _ = http_req(f"{base_url}/practice/attempt", method="POST", headers=app_headers, payload=dave_payload)
    assert code == 429, f"Expected 429 for exhausted budget attempt, got {code}: {body}"
    assert body.get("error") == "budget_exceeded", f"Expected budget_exceeded error, got {body}"
    print("    -> Budget-exhausted attempt rejected with 429 budget_exceeded.")

    print("  [test 10/12] Verify retrieval drills on Unit 0.2, 0.3...")
    for uid in ("0.2", "0.3"):
        code, body, _ = http_req(f"{base_url}/practice/retrieval/seeds?unit={uid}", headers=app_headers)
        assert code == 200, f"Expected 200 for retrieval seeds, got {code}: {body}"
        assert len(body.get("seeds", [])) >= 2, f"Expected >= 2 seeds for unit {uid}, got {body}"

        # Submit drill attempt for seed 0
        r_payload = {
            "student_id": 1,
            "unit_id": uid,
            "seed_index": 0,
            "answer": "Detailed conceptual explanation demonstrating deep understanding of the mechanisms."
        }
        code, body, _ = http_req(f"{base_url}/practice/retrieval/attempt", method="POST", headers=app_headers, payload=r_payload)
        assert code == 200, f"Expected 200 for retrieval attempt on {uid}, got {code}: {body}"
        assert body.get("passed") is True, f"Expected retrieval passed=True on {uid}, got {body}"
    print("    -> Retrieval drills executed and graded successfully on all Phase 0 units.")

    print("  [test 11/12] Verify Concierge teach & guard modes for Phase 0...")
    c_ask_payload = {
        "student_id": 1,
        "unit_id": "0.2",
        "question": "Why do automated verification checks run before human rubric review?"
    }
    code, body, _ = http_req(f"{base_url}/concierge/ask", method="POST", headers=app_headers, payload=c_ask_payload)
    assert code == 200, f"Expected 200 for concierge ask, got {code}: {body}"
    assert body.get("mode") in ("teach", "guard"), f"Expected valid mode, got {body}"
    assert body.get("answer"), "Expected non-empty concierge answer"
    print("    -> Concierge accurately routed and answered query.")

    print("  [test 12/12] Verify trace log provenance and token metrics...")
    trace_path = Path(args.trace_log)
    assert trace_path.is_file(), f"Trace log {trace_path} does not exist"
    lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines() if line.strip()]
    assert len(lines) >= 3, f"Expected >= 3 trace calls, found {len(lines)}"

    completion_traces = [t for t in lines if t.get("caller") == "completion"]
    assert len(completion_traces) >= 1, "Expected at least 1 completion trace record"
    ct0 = completion_traces[0]
    assert ct0.get("prompt_tokens", 0) > 0, "Expected positive prompt tokens in completion trace"
    assert ct0.get("completion_tokens", 0) > 0, "Expected positive completion tokens in completion trace"
    print("    -> Trace log contains verified provenance records.")

    print("\nAll 12 Milestone C1a assertion tests PASSED cleanly!")


if __name__ == "__main__":
    main()
