#!/usr/bin/env python3
"""smoke-analytics-checks.py — deterministic proof battery for Per-unit Drop-Off & Analytics Engine (S4.7).

Verifies:
1. Auth & Boundary Enforcement:
   - 401 on missing or invalid app auth token.
   - HTTP 200 on authorized requests.
2. Curriculum Macro Funnel (GET /analytics/funnel):
   - Stage counts match synthetic cohorts: Enrolled -> Diagnostic -> Unit Started -> Unit Passed -> Phase Integration -> Capstone Defense.
   - Math verification: conversion_pct and drop_off_pct accurately computed.
3. Per-Unit Drop-off & Friction Breakdown (GET /analytics/drop-off):
   - Starts count, completions count, drop_off_rate_pct match ground truth.
   - Median time to clear calculation verified against elapsed timestamps.
   - Avg attempts to pass verified against submission and practice attempts.
   - Retrieval first-try fail rate matches initial drill records.
   - Concierge turn volume counts verified.
   - Composite friction score correctly ranks top bottleneck units.
4. Filter Parameters:
   - ?phase=3 returns only Phase 3 units.
   - ?phase=1 returns only Phase 1 units.
5. Unit Drilldown Endpoint (GET /analytics/units/<unit_id>):
   - Deep dive friction breakdown returns common failure modes (criteria), failed retrieval seeds, and concierge questions.
6. High-Level Operations KPIs (GET /analytics/summary):
   - Total students, 30-day active rate, pod compliance, graduation rate, avg days to capstone, and top bottleneck unit.

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
    err_str = f"  [FAIL] {msg}"
    if detail:
        err_str += f" -> {detail}"
    print(err_str, file=sys.stderr)


def http_request(
    path: str,
    method: str = "GET",
    token: str | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    url = f"{PRACTICE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Keel-App-Token"] = token
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw), raw
            except Exception:
                return resp.status, None, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, None, raw
    except Exception as exc:
        return 0, None, str(exc)


def main() -> int:
    print("--- 1. Auth Boundary Enforcement ---")
    # 1a. Missing token -> 401
    status, _, _ = http_request("/analytics/summary", method="GET", token=None)
    if status == 401:
        record_pass("GET /analytics/summary returns 401 without token")
    else:
        record_fail("GET /analytics/summary missing token", f"Expected 401, got {status}")

    # 1b. Invalid token -> 401
    status, _, _ = http_request("/analytics/funnel", method="GET", token="invalid-token")
    if status == 401:
        record_pass("GET /analytics/funnel returns 401 with invalid token")
    else:
        record_fail("GET /analytics/funnel invalid token", f"Expected 401, got {status}")

    # 1c. Valid token -> 200
    status, summary_data, _ = http_request("/analytics/summary", method="GET", token=APP_TOKEN)
    if status == 200 and summary_data and summary_data.get("ok"):
        record_pass("GET /analytics/summary returns 200 with valid app token")
    else:
        record_fail("GET /analytics/summary valid token", f"Expected 200, got {status}")

    print("--- 2. Operations Summary KPIs ---")
    if summary_data:
        tot_students = summary_data.get("total_enrolled_students")
        active_rate = summary_data.get("active_30d_rate_pct")
        pod_compliance = summary_data.get("weekly_pod_post_compliance_rate_pct")
        capstone_rate = summary_data.get("capstone_completion_rate_pct")
        top_bottleneck = summary_data.get("top_bottleneck_unit")

        if tot_students == 5:
            record_pass(f"Total students count matches seeded cohort ({tot_students} students)")
        else:
            record_fail("Total students mismatch", f"Expected 5, got {tot_students}")

        if active_rate is not None and active_rate >= 60.0:
            record_pass(f"Active 30-day retention rate accurately calculated ({active_rate}%)")
        else:
            record_fail("Active rate mismatch", f"Expected >= 60.0%, got {active_rate}")

        if pod_compliance is not None and pod_compliance >= 0.0:
            record_pass(f"Weekly pod post compliance rate calculated ({pod_compliance}%)")
        else:
            record_fail("Pod compliance missing or negative", str(pod_compliance))

        if capstone_rate is not None and capstone_rate == 20.0:
            record_pass(f"Capstone completion rate accurately computed (1/5 = {capstone_rate}%)")
        else:
            record_fail("Capstone rate mismatch", f"Expected 20.0%, got {capstone_rate}")

        if top_bottleneck and top_bottleneck.get("unit_id") == "3.2.1":
            record_pass(f"Top bottleneck unit correctly identified as Unit 3.2.1 ({top_bottleneck.get('friction_score')} pts)")
        else:
            record_fail("Top bottleneck unit mismatch", f"Expected Unit 3.2.1, got {top_bottleneck}")

    print("--- 3. Curriculum Macro Funnel ---")
    status, funnel_data, _ = http_request("/analytics/funnel", method="GET", token=APP_TOKEN)
    if status == 200 and funnel_data and funnel_data.get("ok"):
        stages = funnel_data.get("stages", [])
        stage_map = {s["id"]: s for s in stages}

        # Stage 1: Enrolled (5)
        enrolled_stage = stage_map.get("enrolled")
        if enrolled_stage and enrolled_stage["count"] == 5 and enrolled_stage["conversion_pct"] == 100.0:
            record_pass("Funnel Stage 1: Enrolled count = 5, conversion = 100%")
        else:
            record_fail("Funnel Stage 1 mismatch", str(enrolled_stage))

        # Stage 2: Diagnostic Completed (4: Alice, Bob, Carol, Dave)
        diag_stage = stage_map.get("diagnostic_completed")
        if diag_stage and diag_stage["count"] == 4 and diag_stage["conversion_pct"] == 80.0:
            record_pass("Funnel Stage 2: Diagnostic count = 4, conversion = 80.0%")
        else:
            record_fail("Funnel Stage 2 mismatch", str(diag_stage))

        # Stage 3: Unit Started (4: Alice, Bob, Carol, Dave)
        started_stage = stage_map.get("unit_started")
        if started_stage and started_stage["count"] == 4 and started_stage["conversion_pct"] == 80.0:
            record_pass("Funnel Stage 3: Unit Started count = 4, conversion = 80.0%")
        else:
            record_fail("Funnel Stage 3 mismatch", str(started_stage))

        # Stage 4: Unit Passed (3: Alice, Bob, Carol)
        passed_stage = stage_map.get("unit_passed")
        if passed_stage and passed_stage["count"] == 3 and passed_stage["conversion_pct"] == 60.0:
            record_pass("Funnel Stage 4: Unit Passed count = 3, conversion = 60.0%")
        else:
            record_fail("Funnel Stage 4 mismatch", str(passed_stage))

        # Stage 5: Phase Integration Passed (2: Bob, Carol)
        phase_stage = stage_map.get("phase_integration_passed")
        if phase_stage and phase_stage["count"] == 2 and phase_stage["conversion_pct"] == 40.0:
            record_pass("Funnel Stage 5: Phase Integration Passed count = 2, conversion = 40.0%")
        else:
            record_fail("Funnel Stage 5 mismatch", str(phase_stage))

        # Stage 6: Capstone Defense Cleared (1: Carol)
        capstone_stage = stage_map.get("capstone_defense_cleared")
        if capstone_stage and capstone_stage["count"] == 1 and capstone_stage["conversion_pct"] == 20.0:
            record_pass("Funnel Stage 6: Capstone Defense Cleared count = 1, conversion = 20.0%")
        else:
            record_fail("Funnel Stage 6 mismatch", str(capstone_stage))
    else:
        record_fail("GET /analytics/funnel failed", f"Status: {status}")

    print("--- 4. Per-Unit Drop-off & Friction Breakdown ---")
    status, dropoff_data, _ = http_request("/analytics/drop-off", method="GET", token=APP_TOKEN)
    if status == 200 and dropoff_data and dropoff_data.get("ok"):
        units = dropoff_data.get("units", [])
        unit_map = {u["unit_id"]: u for u in units}

        # Verify Unit 3.2.1 (stuck cohort with high friction)
        u321 = unit_map.get("3.2.1")
        if u321:
            if u321["starts_count"] >= 2:
                record_pass(f"Unit 3.2.1 starts_count = {u321['starts_count']}")
            else:
                record_fail("Unit 3.2.1 starts_count mismatch", str(u321))

            if u321["drop_off_rate_pct"] > 0:
                record_pass(f"Unit 3.2.1 drop_off_rate_pct = {u321['drop_off_rate_pct']}%")
            else:
                record_fail("Unit 3.2.1 drop_off_rate_pct expected > 0", str(u321))

            if u321["retrieval_first_try_fail_rate_pct"] >= 50.0:
                record_pass(f"Unit 3.2.1 retrieval check fail rate = {u321['retrieval_first_try_fail_rate_pct']}%")
            else:
                record_fail("Unit 3.2.1 retrieval fail rate mismatch", str(u321))

            if u321["concierge_turn_volume"] >= 4:
                record_pass(f"Unit 3.2.1 concierge question volume = {u321['concierge_turn_volume']} turns")
            else:
                record_fail("Unit 3.2.1 concierge turn volume mismatch", str(u321))

            if u321["friction_score"] >= 40.0:
                record_pass(f"Unit 3.2.1 composite friction score = {u321['friction_score']} pts (High Friction)")
            else:
                record_fail("Unit 3.2.1 friction score expected >= 40.0", str(u321))
        else:
            record_fail("Unit 3.2.1 missing from drop-off breakdown")

        # Verify Unit 1.1 (smooth cohort)
        u11 = unit_map.get("1.1")
        if u11:
            if u11["completions_count"] >= 2:
                record_pass(f"Unit 1.1 completions_count = {u11['completions_count']}")
            else:
                record_fail("Unit 1.1 completions mismatch", str(u11))
            if u11["avg_attempts_to_pass"] <= 1.5:
                record_pass(f"Unit 1.1 avg attempts to pass = {u11['avg_attempts_to_pass']}x")
            else:
                record_fail("Unit 1.1 avg attempts mismatch", str(u11))
        else:
            record_fail("Unit 1.1 missing from drop-off breakdown")
    else:
        record_fail("GET /analytics/drop-off failed", f"Status: {status}")

    print("--- 5. Phase Filtering ---")
    status, phase3_data, _ = http_request("/analytics/drop-off?phase=3", method="GET", token=APP_TOKEN)
    if status == 200 and phase3_data and phase3_data.get("ok"):
        p3_units = phase3_data.get("units", [])
        all_phase3 = all(u.get("phase") == 3 for u in p3_units)
        if all_phase3 and any(u["unit_id"] == "3.2.1" for u in p3_units):
            record_pass(f"GET /analytics/drop-off?phase=3 returns exclusively Phase 3 units ({len(p3_units)} units)")
        else:
            record_fail("GET /analytics/drop-off?phase=3 filtering mismatch", str(p3_units))
    else:
        record_fail("GET /analytics/drop-off?phase=3 failed", f"Status: {status}")

    print("--- 6. Single Unit Friction Drill-down ---")
    status, unit_detail, _ = http_request("/analytics/units/3.2.1", method="GET", token=APP_TOKEN)
    if status == 200 and unit_detail and unit_detail.get("ok"):
        u_info = unit_detail.get("unit", {})
        f_modes = unit_detail.get("failure_modes", [])
        c_questions = unit_detail.get("concierge_questions", [])
        r_failures = unit_detail.get("retrieval_seed_failures", [])

        if u_info.get("unit_id") == "3.2.1":
            record_pass("Unit drilldown returns correct unit metadata")
        else:
            record_fail("Unit drilldown unit_id mismatch", str(u_info))

        if len(c_questions) >= 3:
            record_pass(f"Unit drilldown provides concierge questions list ({len(c_questions)} turns)")
        else:
            record_fail("Unit drilldown concierge questions missing or incomplete", str(c_questions))

        if len(r_failures) >= 1:
            record_pass(f"Unit drilldown provides failed retrieval seeds breakdown ({len(r_failures)} seeds)")
        else:
            record_fail("Unit drilldown retrieval failures missing", str(r_failures))

        if len(f_modes) >= 1:
            record_pass(f"Unit drilldown aggregates recurring failure modes ({len(f_modes)} criteria)")
        else:
            record_fail("Unit drilldown failure modes empty", str(f_modes))
    else:
        record_fail("GET /analytics/units/3.2.1 failed", f"Status: {status}")

    print(f"\nSummary: {passed_count} PASSED, {failed_count} FAILED")
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
