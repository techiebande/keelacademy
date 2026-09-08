#!/usr/bin/env python3
"""platform/grading/analytics/engine.py — Analytics & per-unit drop-off engine (S4.7).

Encapsulates analytics aggregation across:
- `events` (spine events: diagnostic.completed, diagnostic.placed, gate.defense_cleared, etc.)
- `progress` (completion progression markers)
- `submissions` & `verdicts` (student project attempts and pass/fail verdicts)
- `practice_attempts` (Layer-1 completion practice attempts)
- `retrieval_attempts` (Layer-2 free-recall drill attempts)
- `concierge_turns` (AI concierge questions and friction mode turns)
- `pod_posts` & `pod_memberships` (weekly pod post accountability compliance)
- `diagnostic_attempts` (initial diagnostic routing)
- `simulations` (discovery-call and defense reps)

Provides:
1. compute_summary(now_override=None) -> High-level operations KPIs
2. compute_macro_funnel(now_override=None) -> Cohort stage conversions
3. compute_dropoff_breakdown(phase=None, now_override=None) -> Per-unit friction breakdown & ranking
4. compute_unit_detail(unit_id, now_override=None) -> Deep dive friction breakdown for a single unit

Stdlib only.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import shared db module
GRADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str

UNIT_RE = re.compile(r"^\d+(\.\d+)+$")

# Canonical curriculum unit list and sequence
CURRICULUM_UNITS = [
    {"id": "0.1", "phase": 0, "title": "Warmup: System Invariant Harness"},
    {"id": "0.2", "phase": 0, "title": "How Grading & Four-Layer Verification Work"},
    {"id": "0.3", "phase": 0, "title": "One-Click Docker Environment Setup"},
    {"id": "1.1", "phase": 1, "title": "Python for AI Engineering & Pydantic"},
    {"id": "1.2", "phase": 1, "title": "Version Control & Collaborative Git"},
    {"id": "1.3", "phase": 1, "title": "HTTP APIs, Webhooks & Rate Limits"},
    {"id": "1.4", "phase": 1, "title": "Async Programming & Concurrency"},
    {"id": "1.5", "phase": 1, "title": "Testing Suites & Code Quality"},
    {"id": "2.1", "phase": 2, "title": "How Transformer Models Work Practically"},
    {"id": "2.2", "phase": 2, "title": "Tokens, Context Windows & Model Physics"},
    {"id": "2.3", "phase": 2, "title": "Provider Landscape & Tradeoffs"},
    {"id": "2.4", "phase": 2, "title": "Calling LLM APIs Like an Engineer"},
    {"id": "2.5", "phase": 2, "title": "Stripe Checkout & Billing Integration"},
    {"id": "2.6", "phase": 2, "title": "Rebate Ledger & Machine Transitions"},
    {"id": "2.7", "phase": 2, "title": "Phase 2 Integration Gate"},
    {"id": "3.1", "phase": 3, "title": "Completion Practice Workbench"},
    {"id": "3.2", "phase": 3, "title": "Retrieval Drills & Judge Evaluation"},
    {"id": "3.3", "phase": 3, "title": "Spaced Re-Checks & Economics"},
    {"id": "3.4", "phase": 3, "title": "Adaptive Practice Routing"},
    {"id": "3.5", "phase": 3, "title": "Phase 3 Concierge Tutor"},
    {"id": "4.1", "phase": 4, "title": "Placement Diagnostic"},
    {"id": "4.2", "phase": 4, "title": "Peer Accountability Pods"},
    {"id": "4.3", "phase": 4, "title": "Weekly Retention Digest"},
    {"id": "4.4", "phase": 4, "title": "Public Build Gallery"},
    {"id": "4.5", "phase": 4, "title": "Discovery Call Simulation Engine"},
    {"id": "4.6", "phase": 4, "title": "Skeptical Reviewer Defenses"},
    {"id": "5.1", "phase": 5, "title": "Function Calling & Tool Schemas"},
    {"id": "5.2", "phase": 5, "title": "Single-Agent Reasoning Loops"},
    {"id": "5.3", "phase": 5, "title": "Multi-Agent Orchestration"},
    {"id": "5.4", "phase": 5, "title": "Orchestration Frameworks"},
    {"id": "5.5", "phase": 5, "title": "Memory & State Design"},
    {"id": "6.1", "phase": 6, "title": "When to Fine-Tune vs RAG"},
    {"id": "6.2", "phase": 6, "title": "Supervised Fine-Tuning Fundamentals"},
    {"id": "6.3", "phase": 6, "title": "LoRA & QLoRA Hands-On"},
    {"id": "6.4", "phase": 6, "title": "Preference-Based Methods (DPO)"},
    {"id": "7.1", "phase": 7, "title": "Golden Datasets & Ground Truth"},
    {"id": "7.2", "phase": 7, "title": "Automated & LLM-as-Judge Evaluation"},
    {"id": "7.3", "phase": 7, "title": "Production Observability & Tracing"},
    {"id": "7.4", "phase": 7, "title": "Regression Testing for Non-Deterministic Systems"},
    {"id": "8.1", "phase": 8, "title": "Token & Cost Modeling"},
    {"id": "8.2", "phase": 8, "title": "Model Routing & Cascading"},
    {"id": "8.3", "phase": 8, "title": "Prompt Caching & Latency Optimization"},
    {"id": "9.1", "phase": 9, "title": "Prompt Injection Defense & Guardrails"},
    {"id": "9.2", "phase": 9, "title": "Standard LLM Risk Categories"},
    {"id": "9.3", "phase": 9, "title": "Human-in-the-Loop Design"},
    {"id": "9.4", "phase": 9, "title": "Audit Trails, Privacy & Governance"},
    {"id": "10.1", "phase": 10, "title": "Production APIs & FastAPI"},
    {"id": "10.2", "phase": 10, "title": "Containerization & GPU Environments"},
    {"id": "10.3", "phase": 10, "title": "CI/CD for Probabilistic Systems"},
    {"id": "10.4", "phase": 10, "title": "Monitoring, Alerting & On-Call"},
    {"id": "11.1", "phase": 11, "title": "Positioning & Niche Selection"},
    {"id": "11.2", "phase": 11, "title": "Architectural Case Studies & Assets"},
    {"id": "11.3", "phase": 11, "title": "Value-Based Pricing Models"},
    {"id": "11.4", "phase": 11, "title": "Prospect Qualification & Outreach"},
    {"id": "11.5", "phase": 11, "title": "Discovery Call Rehearsals"},
    {"id": "11.6", "phase": 11, "title": "Proposals, Contracts & SOW Exclusions"},
    {"id": "11.7", "phase": 11, "title": "Scope & Client Management"},
    {"id": "11.8", "phase": 11, "title": "Retainer Conversion & Maintenance SLAs"},
    {"id": "12.1", "phase": 12, "title": "OmniCart Operations Capstone"},
]

CURRICULUM_MAP = {u["id"]: u for u in CURRICULUM_UNITS}


def get_unit_title(unit_id: str) -> str:
    """Retrieve title for a unit id from phases.yaml or fallback map."""
    try:
        repo_root = GRADING_DIR.parent.parent
        phases_path = repo_root / "content" / "curriculum" / "phases.yaml"
        if phases_path.is_file():
            import yaml
            data = yaml.safe_load(phases_path.read_text(encoding="utf-8"))
            for p in data.get("phases", []):
                for m in p.get("modules", []):
                    if str(m.get("id")) == str(unit_id):
                        return str(m.get("title", f"Unit {unit_id}"))
    except Exception:
        pass
    if unit_id in CURRICULUM_MAP:
        return CURRICULUM_MAP[unit_id]["title"]
    return f"Unit {unit_id}"


def get_unit_phase(unit_id: str) -> int:
    """Parse phase integer from unit id e.g. '3.2.1' -> 3."""
    if unit_id in CURRICULUM_MAP:
        return CURRICULUM_MAP[unit_id]["phase"]
    parts = unit_id.split(".")
    if parts and parts[0].isdigit():
        return int(parts[0])
    return 0


def calculate_friction_score(
    drop_off_rate_pct: float,
    retrieval_first_try_fail_rate_pct: float,
    avg_attempts_to_pass: float,
    concierge_turn_volume: int,
) -> float:
    """Calculate composite friction score (0 to 100).
    
    Formula:
    - Drop-off rate weight: 40% (0..100)
    - Retrieval first-try fail rate weight: 30% (0..100)
    - Excess attempts weight: 20% (max normalized: (avg_attempts - 1) / 3 * 100, clamped 0..100)
    - Concierge volume weight: 10% (concierge_turns normalized: min(100, turns * 10))
    """
    drop_comp = max(0.0, min(100.0, float(drop_off_rate_pct)))
    retrieval_comp = max(0.0, min(100.0, float(retrieval_first_try_fail_rate_pct)))
    
    # Attempts factor: 1 attempt = 0 friction, 4+ attempts = 100 friction
    excess_attempts = max(0.0, avg_attempts_to_pass - 1.0)
    attempts_comp = max(0.0, min(100.0, (excess_attempts / 3.0) * 100.0))
    
    # Concierge volume factor: 10+ questions = 100 friction
    concierge_comp = max(0.0, min(100.0, float(concierge_turn_volume) * 10.0))
    
    score = (
        0.40 * drop_comp
        + 0.30 * retrieval_comp
        + 0.20 * attempts_comp
        + 0.10 * concierge_comp
    )
    return round(score, 1)


def compute_summary(now_override: datetime | None = None) -> dict[str, Any]:
    """Compute high-level operations KPIs.
    
    - total_enrolled_students
    - active_30d_students
    - active_30d_rate_pct
    - pod_post_compliance_rate_pct
    - capstone_completion_rate_pct
    - top_bottleneck_unit
    - avg_days_to_capstone
    """
    now_dt = now_override or datetime.now(timezone.utc)
    now_sql = sql_str(now_dt.isoformat())

    sql = f"""BEGIN;
-- 1. Total unique students enrolled or registered
SELECT count(DISTINCT id) FROM students;

-- 2. 30-day active students (any submission, practice, retrieval, concierge, simulation, or pod post within 30 days)
SELECT count(DISTINCT student_id) FROM (
    SELECT student_id FROM submissions WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
    UNION
    SELECT student_id FROM practice_attempts WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
    UNION
    SELECT student_id FROM retrieval_attempts WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
    UNION
    SELECT student_id FROM concierge_turns WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
    UNION
    SELECT student_id FROM simulations WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
    UNION
    SELECT student_id FROM pod_posts WHERE created_at >= ({now_sql}::timestamptz - interval '30 days')
) active_students;

-- 3. Pod post compliance: ratio of submitted posts to total expected pod member-weeks
SELECT 
    coalesce(count(DISTINCT pp.id), 0) AS total_posts,
    coalesce(count(DISTINCT pm.student_id), 0) AS active_members
FROM pod_memberships pm
LEFT JOIN pod_posts pp ON pp.student_id = pm.student_id
WHERE pm.active = true;

-- 4. Capstone completions & avg duration to capstone clearance
SELECT 
    count(DISTINCT s.student_id) AS capstone_pass_count,
    avg(EXTRACT(EPOCH FROM (v.issued_at - st.created_at)) / 86400.0) AS avg_days
FROM submissions s
JOIN verdicts v ON v.submission_id = s.id AND v.overall = 'pass'
JOIN students st ON st.id = s.student_id
WHERE s.unit_id = '12.1';

ROLLBACK;
"""
    rows = db_sql(sql)
    
    total_students = int(rows[0][0]) if rows and len(rows) > 0 and rows[0][0] else 0
    active_30d = int(rows[1][0]) if rows and len(rows) > 1 and rows[1][0] else 0
    active_rate = round((active_30d / total_students * 100.0), 1) if total_students > 0 else 0.0

    pod_stats = rows[2] if rows and len(rows) > 2 else (0, 0)
    total_posts = int(pod_stats[0]) if pod_stats[0] else 0
    active_members = int(pod_stats[1]) if pod_stats[1] else 0
    pod_compliance = round(min(100.0, (total_posts / max(1, active_members)) * 100.0), 1) if active_members > 0 else 0.0

    capstone_stats = rows[3] if rows and len(rows) > 3 else (0, None)
    capstone_completions = int(capstone_stats[0]) if capstone_stats[0] else 0
    capstone_rate = round((capstone_completions / total_students * 100.0), 1) if total_students > 0 else 0.0
    avg_days_to_capstone = round(float(capstone_stats[1]), 1) if capstone_stats[1] is not None else 0.0

    # Get dropoff breakdown to discover top bottleneck unit
    dropoff_data = compute_dropoff_breakdown(now_override=now_override)
    top_bottleneck = dropoff_data["top_bottleneck_unit"] if dropoff_data.get("units") else None

    return {
        "ok": True,
        "total_enrolled_students": total_students,
        "active_30d_students": active_30d,
        "active_30d_rate_pct": active_rate,
        "weekly_pod_post_compliance_rate_pct": pod_compliance,
        "capstone_completion_rate_pct": capstone_rate,
        "total_capstone_graduates": capstone_completions,
        "avg_days_to_capstone": avg_days_to_capstone,
        "top_bottleneck_unit": top_bottleneck,
        "generated_at": now_dt.isoformat(),
    }


def compute_macro_funnel(now_override: datetime | None = None) -> dict[str, Any]:
    """Compute Curriculum Macro Funnel stage conversions:
    1. Enrolled / Registered Students
    2. Diagnostic Completed
    3. Unit Started (at least 1 interaction on any unit)
    4. Unit Passed (at least 1 passing verdict/unit completion)
    5. Phase Integration Passed (cleared any phase gate: 1.5, 2.7, 5.1, or 12.1)
    6. Capstone Defense Cleared (passed skeptical reviewer defense gate / 12.1)
    """
    now_dt = now_override or datetime.now(timezone.utc)

    sql = """BEGIN;
-- 1. Enrolled students
SELECT count(DISTINCT id) FROM students;

-- 2. Diagnostic completed (either via diagnostic_attempts or diagnostic.completed / diagnostic.placed events)
SELECT count(DISTINCT student_id) FROM (
    SELECT student_id FROM diagnostic_attempts
    UNION
    SELECT (payload->>'student_id')::bigint FROM events WHERE type IN ('diagnostic.completed', 'diagnostic.placed')
) diag_students;

-- 3. Unit Started (started any practice, retrieval, submission, or concierge)
SELECT count(DISTINCT student_id) FROM (
    SELECT student_id FROM submissions
    UNION
    SELECT student_id FROM practice_attempts
    UNION
    SELECT student_id FROM retrieval_attempts
    UNION
    SELECT student_id FROM concierge_turns
) started_students;

-- 4. Unit Passed (passed any verified submission or practice or progress passed)
SELECT count(DISTINCT student_id) FROM (
    SELECT s.student_id FROM submissions s JOIN verdicts v ON v.submission_id = s.id WHERE v.overall = 'pass'
    UNION
    SELECT student_id FROM practice_attempts WHERE passed = true
    UNION
    SELECT student_id FROM progress WHERE state = 'passed'
    UNION
    SELECT student_id FROM unlocked_units
) passed_students;

-- 5. Phase Integration Passed (passed 1.5, 2.7, 5.1, or 12.1)
SELECT count(DISTINCT student_id) FROM (
    SELECT s.student_id FROM submissions s JOIN verdicts v ON v.submission_id = s.id 
    WHERE v.overall = 'pass' AND s.unit_id IN ('1.5', '2.7', '5.1', '12.1')
    UNION
    SELECT (payload->>'student_id')::bigint FROM events 
    WHERE type = 'gate.passed'
) phase_gate_students;

-- 6. Capstone Defense Cleared (passed 12.1 or gate.defense_cleared)
SELECT count(DISTINCT student_id) FROM (
    SELECT s.student_id FROM submissions s JOIN verdicts v ON v.submission_id = s.id 
    WHERE v.overall = 'pass' AND s.unit_id = '12.1'
    UNION
    SELECT (payload->>'student_id')::bigint FROM events 
    WHERE type = 'gate.defense_cleared'
) capstone_students;

ROLLBACK;
"""
    rows = db_sql(sql)

    enrolled = int(rows[0][0]) if rows and len(rows) > 0 and rows[0][0] else 0
    diag_completed = int(rows[1][0]) if rows and len(rows) > 1 and rows[1][0] else 0
    unit_started = int(rows[2][0]) if rows and len(rows) > 2 and rows[2][0] else 0
    unit_passed = int(rows[3][0]) if rows and len(rows) > 3 and rows[3][0] else 0
    phase_passed = int(rows[4][0]) if rows and len(rows) > 4 and rows[4][0] else 0
    capstone_cleared = int(rows[5][0]) if rows and len(rows) > 5 and rows[5][0] else 0

    base_count = max(1, enrolled)

    stages = [
        {
            "id": "enrolled",
            "name": "Enrolled",
            "count": enrolled,
            "conversion_pct": 100.0,
            "drop_off_pct": 0.0,
        },
        {
            "id": "diagnostic_completed",
            "name": "Diagnostic Completed",
            "count": diag_completed,
            "conversion_pct": round((diag_completed / base_count) * 100.0, 1),
            "drop_off_pct": round(max(0.0, ((enrolled - diag_completed) / base_count) * 100.0), 1),
        },
        {
            "id": "unit_started",
            "name": "Unit Started",
            "count": unit_started,
            "conversion_pct": round((unit_started / base_count) * 100.0, 1),
            "drop_off_pct": round(max(0.0, ((diag_completed - unit_started) / base_count) * 100.0), 1),
        },
        {
            "id": "unit_passed",
            "name": "Unit Passed",
            "count": unit_passed,
            "conversion_pct": round((unit_passed / base_count) * 100.0, 1),
            "drop_off_pct": round(max(0.0, ((unit_started - unit_passed) / base_count) * 100.0), 1),
        },
        {
            "id": "phase_integration_passed",
            "name": "Phase Integration Passed",
            "count": phase_passed,
            "conversion_pct": round((phase_passed / base_count) * 100.0, 1),
            "drop_off_pct": round(max(0.0, ((unit_passed - phase_passed) / base_count) * 100.0), 1),
        },
        {
            "id": "capstone_defense_cleared",
            "name": "Capstone Defense Cleared",
            "count": capstone_cleared,
            "conversion_pct": round((capstone_cleared / base_count) * 100.0, 1),
            "drop_off_pct": round(max(0.0, ((phase_passed - capstone_cleared) / base_count) * 100.0), 1),
        },
    ]

    return {
        "ok": True,
        "total_enrolled": enrolled,
        "stages": stages,
        "generated_at": now_dt.isoformat(),
    }


def compute_dropoff_breakdown(
    phase: int | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Compute per-unit drop-off and friction metrics across all or phase-filtered units.
    
    Returns:
    - units: List of UnitFrictionRecord sorted by friction_score descending.
    - top_bottleneck_unit: Record for the unit with highest friction score.
    - total_units_tracked: Count of units evaluated.
    """
    now_dt = now_override or datetime.now(timezone.utc)

    # 1. Query per-unit raw data from DB
    # Starts: unique students with ANY interaction on the unit (submission, practice, retrieval, concierge, unlocked)
    # Completions: unique students with a passing verdict on submissions OR passed practice_attempt OR passed progress
    # Attempts: total submission + practice attempts / completions count
    # Retrieval first-try fail rate: first attempt per (student_id, unit_id, seed_index) failing
    # Concierge turn volume: total count of concierge_turns for unit
    # Time to clear: hours from first interaction timestamp to first passing verdict timestamp per student

    sql = """BEGIN;
-- All unit interactions (enrollments, submissions, practice_attempts, retrieval_attempts, concierge_turns, unlocked_units, progress)
WITH unit_interactions AS (
    SELECT student_id, unit_id, enrolled_at as created_at, 'enrollment' as source FROM enrollments
    UNION ALL
    SELECT student_id, unit_id, created_at, 'submission' as source FROM submissions
    UNION ALL
    SELECT student_id, unit_id, created_at, 'practice' as source FROM practice_attempts
    UNION ALL
    SELECT student_id, unit_id, created_at, 'retrieval' as source FROM retrieval_attempts
    UNION ALL
    SELECT student_id, unit_id, created_at, 'concierge' as source FROM concierge_turns
    UNION ALL
    SELECT student_id, unit_id, coalesce(unlocked_at, '2026-01-01'::timestamptz) as created_at, 'progress' as source FROM progress
    UNION ALL
    SELECT student_id, unit_id, unlocked_at as created_at, 'unlocked_units' as source FROM unlocked_units
),
unit_completions AS (
    SELECT s.student_id, s.unit_id, min(v.issued_at) as passed_at
    FROM submissions s
    JOIN verdicts v ON v.submission_id = s.id
    WHERE v.overall = 'pass'
    GROUP BY s.student_id, s.unit_id
    UNION
    SELECT pa.student_id, pa.unit_id, min(pa.created_at) as passed_at
    FROM practice_attempts pa
    WHERE pa.passed = true
    GROUP BY pa.student_id, pa.unit_id
    UNION
    SELECT pr.student_id, pr.unit_id, min(pr.passed_at) as passed_at
    FROM progress pr
    WHERE pr.state = 'passed' AND pr.passed_at IS NOT NULL
    GROUP BY pr.student_id, pr.unit_id
),
retrieval_ranked AS (
    SELECT 
        student_id, unit_id, seed_index, passed,
        row_number() OVER (PARTITION BY student_id, unit_id, seed_index ORDER BY id ASC, created_at ASC) as drill_attempt_num
    FROM retrieval_attempts
),
submission_counts AS (
    SELECT unit_id, count(*) as sub_count
    FROM submissions
    GROUP BY unit_id
),
practice_counts AS (
    SELECT unit_id, count(*) as prac_count
    FROM practice_attempts
    GROUP BY unit_id
),
concierge_counts AS (
    SELECT unit_id, count(*) as turn_vol
    FROM concierge_turns
    GROUP BY unit_id
),
unit_starts AS (
    SELECT unit_id, count(DISTINCT student_id) as starts_cnt
    FROM unit_interactions
    GROUP BY unit_id
),
unit_clears AS (
    SELECT unit_id, count(DISTINCT student_id) as completions_cnt
    FROM unit_completions
    GROUP BY unit_id
)
SELECT
    us.unit_id,
    us.starts_cnt,
    coalesce(uc.completions_cnt, 0) as completions_count,
    coalesce(cc.turn_vol, 0) as concierge_turns_count,
    coalesce(sc.sub_count, 0) + coalesce(pc.prac_count, 0) as total_attempts
FROM unit_starts us
LEFT JOIN unit_clears uc ON uc.unit_id = us.unit_id
LEFT JOIN concierge_counts cc ON cc.unit_id = us.unit_id
LEFT JOIN submission_counts sc ON sc.unit_id = us.unit_id
LEFT JOIN practice_counts pc ON pc.unit_id = us.unit_id;

-- Retrieval first-try drill fails
WITH retrieval_ranked AS (
    SELECT 
        unit_id, passed,
        row_number() OVER (PARTITION BY student_id, unit_id, seed_index ORDER BY id ASC, created_at ASC) as drill_attempt_num
    FROM retrieval_attempts
)
SELECT 
    unit_id,
    count(*) as total_first_drills,
    count(*) FILTER (WHERE passed = false) as failed_first_drills
FROM retrieval_ranked
WHERE drill_attempt_num = 1
GROUP BY unit_id;

-- Time to clear per student (hours)
WITH u_starts AS (
    SELECT student_id, unit_id, min(created_at) as started_at
    FROM (
        SELECT student_id, unit_id, enrolled_at as created_at FROM enrollments
        UNION ALL
        SELECT student_id, unit_id, created_at FROM submissions
        UNION ALL
        SELECT student_id, unit_id, created_at FROM practice_attempts
        UNION ALL
        SELECT student_id, unit_id, created_at FROM retrieval_attempts
    ) starts
    GROUP BY student_id, unit_id
),
u_passes AS (
    SELECT s.student_id, s.unit_id, min(v.issued_at) as cleared_at
    FROM submissions s
    JOIN verdicts v ON v.submission_id = s.id
    WHERE v.overall = 'pass'
    GROUP BY s.student_id, s.unit_id
    UNION
    SELECT pa.student_id, pa.unit_id, min(pa.created_at) as cleared_at
    FROM practice_attempts pa
    WHERE pa.passed = true
    GROUP BY pa.student_id, pa.unit_id
)
SELECT 
    s.unit_id,
    EXTRACT(EPOCH FROM (p.cleared_at - s.started_at)) / 3600.0 as hours_to_clear
FROM u_starts s
JOIN u_passes p ON p.student_id = s.student_id AND p.unit_id = s.unit_id
WHERE p.cleared_at >= s.started_at;

ROLLBACK;
"""
    results = db_sql(sql)

    # Parse raw aggregates
    unit_raw_map: dict[str, dict[str, Any]] = {}

    for r in results:
        # Check query block based on column count
        if len(r) == 5:
            # Main unit interactions query
            uid = str(r[0])
            starts = int(r[1])
            completions = int(r[2])
            concierge_vol = int(r[3])
            total_atts = int(r[4])
            unit_raw_map[uid] = {
                "unit_id": uid,
                "starts_count": starts,
                "completions_count": completions,
                "concierge_turn_volume": concierge_vol,
                "total_attempts": total_atts,
                "total_first_drills": 0,
                "failed_first_drills": 0,
                "durations": [],
            }
        elif len(r) == 3:
            # Retrieval first-try stats
            uid = str(r[0])
            tot_drills = int(r[1])
            fail_drills = int(r[2])
            if uid in unit_raw_map:
                unit_raw_map[uid]["total_first_drills"] = tot_drills
                unit_raw_map[uid]["failed_first_drills"] = fail_drills
            else:
                unit_raw_map[uid] = {
                    "unit_id": uid,
                    "starts_count": 0,
                    "completions_count": 0,
                    "concierge_turn_volume": 0,
                    "total_attempts": 0,
                    "total_first_drills": tot_drills,
                    "failed_first_drills": fail_drills,
                    "durations": [],
                }
        elif len(r) == 2:
            # Time to clear durations
            uid = str(r[0])
            hrs = float(r[1]) if r[1] is not None else 0.0
            if uid in unit_raw_map:
                unit_raw_map[uid]["durations"].append(hrs)
            else:
                unit_raw_map[uid] = {
                    "unit_id": uid,
                    "starts_count": 0,
                    "completions_count": 0,
                    "concierge_turn_volume": 0,
                    "total_attempts": 0,
                    "total_first_drills": 0,
                    "failed_first_drills": 0,
                    "durations": [hrs],
                }

    # Merge with full canonical units if no interactions exist yet to guarantee complete reporting
    all_unit_ids = set(unit_raw_map.keys()) | {u["id"] for u in CURRICULUM_UNITS}

    unit_records: list[dict[str, Any]] = []

    for uid in all_unit_ids:
        unit_ph = get_unit_phase(uid)
        if phase is not None and unit_ph != phase:
            continue

        raw = unit_raw_map.get(uid, {
            "unit_id": uid,
            "starts_count": 0,
            "completions_count": 0,
            "concierge_turn_volume": 0,
            "total_attempts": 0,
            "total_first_drills": 0,
            "failed_first_drills": 0,
            "durations": [],
        })

        starts = raw["starts_count"]
        completions = min(starts, raw["completions_count"]) if starts > 0 else raw["completions_count"]
        effective_starts = max(starts, completions)

        # Drop-off rate %
        if effective_starts > 0:
            drop_off_pct = round(((effective_starts - completions) / effective_starts) * 100.0, 1)
        else:
            drop_off_pct = 0.0

        # Retrieval fail rate %
        tot_drills = raw["total_first_drills"]
        fail_drills = raw["failed_first_drills"]
        if tot_drills > 0:
            retrieval_fail_pct = round((fail_drills / tot_drills) * 100.0, 1)
        else:
            retrieval_fail_pct = 0.0

        # Avg attempts to pass
        if completions > 0:
            avg_attempts = round(max(1.0, float(raw["total_attempts"]) / float(completions)), 2)
        elif effective_starts > 0 and raw["total_attempts"] > 0:
            avg_attempts = round(float(raw["total_attempts"]) / float(effective_starts), 2)
        else:
            avg_attempts = 1.0

        # Median time to clear (hours)
        durations = raw["durations"]
        if durations:
            sorted_durations = sorted(durations)
            n = len(sorted_durations)
            if n % 2 == 1:
                median_hrs = sorted_durations[n // 2]
            else:
                median_hrs = (sorted_durations[(n // 2) - 1] + sorted_durations[n // 2]) / 2.0
            median_hrs = round(max(0.1, median_hrs), 1)
        else:
            median_hrs = 0.0

        concierge_vol = raw["concierge_turn_volume"]

        friction_score = calculate_friction_score(
            drop_off_rate_pct=drop_off_pct,
            retrieval_first_try_fail_rate_pct=retrieval_fail_pct,
            avg_attempts_to_pass=avg_attempts,
            concierge_turn_volume=concierge_vol,
        )

        title = get_unit_title(uid)

        unit_records.append({
            "unit_id": uid,
            "title": title,
            "phase": unit_ph,
            "starts_count": effective_starts,
            "completions_count": completions,
            "drop_off_rate_pct": drop_off_pct,
            "median_time_to_clear_hrs": median_hrs,
            "avg_attempts_to_pass": avg_attempts,
            "retrieval_first_try_fail_rate_pct": retrieval_fail_pct,
            "concierge_turn_volume": concierge_vol,
            "friction_score": friction_score,
        })

    # Sort units by friction_score descending, then starts_count descending
    unit_records.sort(key=lambda x: (x["friction_score"], x["drop_off_rate_pct"], x["starts_count"]), reverse=True)

    top_bottleneck = unit_records[0] if unit_records else None

    return {
        "ok": True,
        "phase": phase,
        "total_units_tracked": len(unit_records),
        "top_bottleneck_unit": top_bottleneck,
        "units": unit_records,
        "generated_at": now_dt.isoformat(),
    }


def compute_unit_detail(
    unit_id: str,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Compute detailed friction drilldown for a single unit.
    
    Includes:
    - Base metrics (starts, completions, drop_off, avg_attempts, retrieval_fail_pct, etc.)
    - Common failure modes: breakdown of failing criteria from Layer-1 checks & LLM judge verdicts
    - Common concierge questions and themes
    - Retrieval drill failure breakdown per seed prompt
    """
    now_dt = now_override or datetime.now(timezone.utc)
    clean_uid = unit_id.strip()

    # 1. Fetch unit basic stats from dropoff engine
    breakdown = compute_dropoff_breakdown(now_override=now_override)
    matched_unit = next((u for u in breakdown["units"] if u["unit_id"] == clean_uid), None)

    if not matched_unit:
        # Create empty stub
        matched_unit = {
            "unit_id": clean_uid,
            "title": get_unit_title(clean_uid),
            "phase": get_unit_phase(clean_uid),
            "starts_count": 0,
            "completions_count": 0,
            "drop_off_rate_pct": 0.0,
            "median_time_to_clear_hrs": 0.0,
            "avg_attempts_to_pass": 1.0,
            "retrieval_first_try_fail_rate_pct": 0.0,
            "concierge_turn_volume": 0,
            "friction_score": 0.0,
        }

    # 2. Query specific failure modes, concierge questions, and retrieval seed failures for this unit
    # Distinguish rows by querying with clear kind discriminator
    sql = f"""BEGIN;
-- Concierge questions asked on this unit
SELECT 'concierge' as kind, id::text, student_id::text, mode, question, created_at::text
FROM concierge_turns
WHERE unit_id = {sql_str(clean_uid)}
ORDER BY id DESC
LIMIT 50;

-- Failed verdicts criteria for submissions on this unit
SELECT 'verdict' as kind, v.id::text, v.submission_id::text, v.rubric_id, v.verdict_json::text, v.issued_at::text
FROM verdicts v
JOIN submissions s ON s.id = v.submission_id
WHERE s.unit_id = {sql_str(clean_uid)} AND v.overall = 'fail'
ORDER BY v.id DESC
LIMIT 50;

-- Failed retrieval drill seeds on this unit
SELECT 'retrieval' as kind, seed_index::text, seed_prompt, student_answer, feedback, coalesce(evidence, '')
FROM retrieval_attempts
WHERE unit_id = {sql_str(clean_uid)} AND passed = false
ORDER BY id DESC
LIMIT 50;

-- Failed practice attempt checks on this unit
SELECT 'practice' as kind, id::text, student_id::text, pass_count::text, total_checks::text, results_json::text
FROM practice_attempts
WHERE unit_id = {sql_str(clean_uid)} AND passed = false
ORDER BY id DESC
LIMIT 50;

ROLLBACK;
"""
    results = db_sql(sql)

    concierge_questions = []
    failure_modes: list[dict[str, Any]] = []
    seed_failures: list[dict[str, Any]] = []

    for r in results:
        kind = r[0]
        if kind == "concierge":
            concierge_questions.append({
                "id": int(r[1]),
                "student_id": int(r[2]),
                "mode": r[3],
                "question": r[4],
                "created_at": str(r[5]),
            })
        elif kind == "retrieval":
            seed_failures.append({
                "seed_index": int(r[1]) if r[1].isdigit() else 0,
                "seed_prompt": r[2],
                "student_answer": r[3],
                "feedback": r[4],
                "evidence": r[5],
            })
        elif kind == "verdict":
            try:
                v_json = json.loads(r[4])
                judge_data = v_json.get("judge") or {}
                for crit in judge_data.get("criteria", []):
                    if crit.get("verdict") == "fail":
                        failure_modes.append({
                            "type": "judge_criterion",
                            "criterion_id": crit.get("id") or "eval_criterion",
                            "reason": crit.get("evidence") or crit.get("notes") or "Criterion failed judge verification",
                        })
                layer1_data = v_json.get("layer1") or {}
                for chk in layer1_data.get("checks", []):
                    if chk.get("status") in ("fail", "error"):
                        failure_modes.append({
                            "type": "layer1_check",
                            "criterion_id": chk.get("id") or "layer1_check",
                            "reason": chk.get("note") or chk.get("output") or "Deterministic check failed",
                        })
            except Exception:
                pass
        elif kind == "practice":
            try:
                checks_json = json.loads(r[5])
                if isinstance(checks_json, list):
                    for chk in checks_json:
                        if chk.get("status") in ("fail", "error") or chk.get("passed") is False:
                            failure_modes.append({
                                "type": "practice_check",
                                "criterion_id": chk.get("id") or chk.get("name") or "sandbox_check",
                                "reason": chk.get("note") or chk.get("error") or chk.get("message") or "Check failed",
                            })
            except Exception:
                pass

    # Group failure modes by criterion
    grouped_failure_modes: dict[str, dict[str, Any]] = {}
    for fm in failure_modes:
        cid = fm["criterion_id"]
        if cid not in grouped_failure_modes:
            grouped_failure_modes[cid] = {
                "criterion_id": cid,
                "type": fm["type"],
                "occurrences": 0,
                "sample_reasons": [],
            }
        grouped_failure_modes[cid]["occurrences"] += 1
        if len(grouped_failure_modes[cid]["sample_reasons"]) < 3 and fm["reason"]:
            grouped_failure_modes[cid]["sample_reasons"].append(fm["reason"])

    sorted_failure_modes = sorted(grouped_failure_modes.values(), key=lambda x: x["occurrences"], reverse=True)

    return {
        "ok": True,
        "unit": matched_unit,
        "failure_modes": sorted_failure_modes,
        "retrieval_seed_failures": seed_failures[:20],
        "concierge_questions": concierge_questions[:20],
        "generated_at": now_dt.isoformat(),
    }
