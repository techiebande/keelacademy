#!/usr/bin/env python3
"""community/digests.py — Personalized weekly retention digest synthesizer & delivery engine (S4.3).

Synthesizes weekly personalized digests across the 4 mandatory pillars:
1. Current Location: Completed units, active unit, current route step.
2. Next Unlocks: What comes next on the curriculum map and routing path.
3. Pod Activity: Highlights of what peers shipped/broke/planned this week from pod_posts.
4. Rebate & Streak Status: Pledged/earned rebate milestones and deadline timers.

Guaranteed Idle Reach-out:
Synthesizes and dispatches for ALL enrolled students regardless of login activity
or attempts made during the week.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GRADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str
from community.email_transport import deliver_email
from community.pods import current_cohort_week

# Phase and unit curriculum map structure for location and unlock calculation
CURRICULUM_UNITS = [
    {"id": "0.1", "phase": 0, "title": "Warmup: System Invariant Harness"},
    {"id": "1.1", "phase": 1, "title": "Pydantic Extraction Parser"},
    {"id": "1.2", "phase": 1, "title": "Deterministic Sandbox Checks"},
    {"id": "1.3", "phase": 1, "title": "API Budgets & Spending Caps"},
    {"id": "1.4", "phase": 1, "title": "Immutable Events Spine"},
    {"id": "1.5", "phase": 1, "title": "Phase 1 Integration Gate"},
    {"id": "2.1", "phase": 2, "title": "Async Task Queue & Workers"},
    {"id": "2.2", "phase": 2, "title": "Live Log Stream & SSE"},
    {"id": "2.3", "phase": 2, "title": "Submission History & Status"},
    {"id": "2.4", "phase": 2, "title": "Managed Auth & Identities"},
    {"id": "2.5", "phase": 2, "title": "Stripe Checkout & Billing"},
    {"id": "2.6", "phase": 2, "title": "Rebate Ledger & Transitions"},
    {"id": "2.7", "phase": 2, "title": "Phase 2 Integration Gate"},
    {"id": "3.1", "phase": 3, "title": "Completion Practice Workbench"},
    {"id": "3.2", "phase": 3, "title": "Retrieval Drills & Judge"},
    {"id": "3.3", "phase": 3, "title": "Spaced Re-Checks & Economics"},
    {"id": "3.4", "phase": 3, "title": "Adaptive Practice Routing"},
    {"id": "3.5", "phase": 3, "title": "Phase 3 Concierge Tutor"},
    {"id": "4.1", "phase": 4, "title": "Placement Diagnostic"},
    {"id": "4.2", "phase": 4, "title": "Peer Accountability Pods"},
    {"id": "4.3", "phase": 4, "title": "Weekly Retention Digest"},
    {"id": "5.1", "phase": 5, "title": "Phase 5 Multi-Agent Triage Gate"},
    {"id": "12.1", "phase": 12, "title": "OmniCart Operations Capstone"},
]

CURRICULUM_MAP = {u["id"]: u for u in CURRICULUM_UNITS}
UNIT_ORDER = [u["id"] for u in CURRICULUM_UNITS]


def synthesize_student_digest(
    student_id: int,
    cohort_week: str | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Synthesize the 4-pillar personalized weekly digest for a single student.
    
    Guaranteed idle reach-out: synthesizes complete and encouraging state even if
    student has 0 attempts/submissions this week.
    """
    effective_week = cohort_week or current_cohort_week(now_override)
    ref_dt = now_override or datetime.now(timezone.utc)

    # 1. Fetch student info
    st_sql = f"BEGIN; SELECT id, display_name, email, created_at::text FROM students WHERE id = {student_id}; ROLLBACK;"
    st_rows = db_sql(st_sql)
    if not st_rows:
        raise ValueError("student_not_found")

    _, raw_name, email, st_created = st_rows[0]
    display_name = raw_name if raw_name else email.split("@")[0]

    # 2. Fetch enrollments, passed progress, latest attempts/submissions
    enr_sql = f"""BEGIN;
SELECT unit_id, status FROM enrollments WHERE student_id = {student_id};
SELECT unit_id, state, passed_at::text FROM progress WHERE student_id = {student_id};
SELECT unit_id, gate_id, unlocked_at::text FROM unlocked_units WHERE student_id = {student_id};
ROLLBACK;
"""
    enr_rows = db_sql(enr_sql)

    enrolled_units = [r[0] for r in enr_rows if len(r) == 2 and r[1] == "active"]
    passed_units = [r[0] for r in enr_rows if len(r) == 3 and r[1] == "passed"]
    unlocked_unit_ids = [r[0] for r in enr_rows if len(r) == 3 and r[1] not in ("passed", "locked")]

    # Combine passed units from progress and verdicts
    passed_set = set(passed_units)
    unlocked_set = set(unlocked_unit_ids) | set(enrolled_units)

    # Activity queries (submissions, practice attempts, retrieval attempts in the last 7 days or total)
    act_sql = f"""BEGIN;
SELECT count(*) FROM submissions WHERE student_id = {student_id};
SELECT count(*) FROM practice_attempts WHERE student_id = {student_id};
SELECT count(*) FROM retrieval_attempts WHERE student_id = {student_id};
SELECT count(*) FROM pod_posts WHERE student_id = {student_id};
ROLLBACK;
"""
    act_rows = db_sql(act_sql)
    recent_activity_count = sum(int(r[0]) for r in act_rows if r and str(r[0]).isdigit())

    is_idle = (recent_activity_count == 0)

    # Determine current active unit
    # Find first enrolled/unlocked unit in order that is NOT passed
    active_unit = None
    for uid in UNIT_ORDER:
        if (uid in enrolled_units or uid in unlocked_set) and uid not in passed_set:
            active_unit = uid
            break

    if not active_unit:
        for uid in UNIT_ORDER:
            if uid not in passed_set:
                active_unit = uid
                break

    # If all enrolled/known units are passed, check if capstone or all done
    is_route_completed = (len(passed_set) >= 3 and (active_unit is None or "12.1" in passed_set)) or ("12.1" in passed_set)
    if is_route_completed and (not active_unit or active_unit == "12.1"):
        active_unit = "12.1"

    if not active_unit:
        active_unit = enrolled_units[0] if enrolled_units else "0.1"

    unit_title = CURRICULUM_MAP.get(active_unit, {}).get("title", f"Unit {active_unit}")

    # Determine current route step
    if is_route_completed:
        current_step = "Build & Capstone Verification"
        location_headline = f"Route Completed — Capstone Verified & Build Bench Open"
        idle_note = "All milestone targets cleared. Ready for production deployment and open bench tinkering."
    elif is_idle:
        current_step = "Practice Retrieval & Workbench"
        location_headline = f"Ready to resume at Unit {active_unit} ({unit_title})"
        idle_note = f"You haven't logged in this week — take 10 minutes to run the practice workbench for Unit {active_unit}."
    else:
        current_step = "Unit Practice Workbench & Harness"
        location_headline = f"Active at Unit {active_unit} ({unit_title})"
        idle_note = f"Great momentum! Continue advancing through Unit {active_unit} practice route."

    # Pillar 1: Current Location
    pillar_current_location = {
        "active_unit": active_unit,
        "active_unit_title": unit_title,
        "completed_units": sorted(list(passed_set)),
        "completed_count": len(passed_set),
        "current_route_step": current_step,
        "is_idle": is_idle,
        "is_completed": is_route_completed,
        "headline": location_headline,
        "note": idle_note,
    }

    # Pillar 2: Next Unlocks
    # Find next 1-3 units after active_unit in the curriculum map
    active_idx = UNIT_ORDER.index(active_unit) if active_unit in UNIT_ORDER else 0
    next_candidates = UNIT_ORDER[active_idx + 1: active_idx + 4]
    next_unlocks_list = []
    for n_id in next_candidates:
        u_info = CURRICULUM_MAP.get(n_id, {})
        next_unlocks_list.append({
            "unit_id": n_id,
            "title": u_info.get("title", f"Unit {n_id}"),
            "phase": u_info.get("phase", 1),
            "description": f"Unlocks next on your track upon clearing Unit {active_unit}.",
        })

    if not next_unlocks_list and is_route_completed:
        next_unlocks_list.append({
            "unit_id": "capstone",
            "title": "Graduate Alumni Network & Capstone Showcase",
            "phase": 13,
            "description": "All 13 phases unlocked. Showcase your verified codebase to hiring partners.",
        })

    pillar_next_unlocks = {
        "next_units": next_unlocks_list,
        "next_phase": CURRICULUM_MAP.get(next_candidates[0], {}).get("phase", 1) if next_candidates else 13,
        "summary": f"Passing Unit {active_unit} unlocks {', '.join(u['unit_id'] for u in next_unlocks_list)}.",
    }

    # Pillar 3: Pod Activity (Highlights from pod_posts this week)
    pod_sql = f"""BEGIN;
SELECT p.id, p.name, p.cohort_week
FROM pod_memberships pm
JOIN pods p ON p.id = pm.pod_id
WHERE pm.student_id = {student_id} AND pm.active = true
LIMIT 1;
ROLLBACK;
"""
    pod_rows = db_sql(pod_sql)
    pod_name = "Independent Track"
    pod_id = None
    pod_highlights = []

    if pod_rows:
        pod_id = int(pod_rows[0][0])
        pod_name = pod_rows[0][1]
        
        # Fetch posts from this pod
        posts_sql = f"""BEGIN;
SELECT pp.id, pp.student_id, s.display_name, s.email, pp.week_number,
       pp.shipped_text, pp.broke_text, pp.next_text, pp.created_at::text
FROM pod_posts pp
JOIN students s ON s.id = pp.student_id
WHERE pp.pod_id = {pod_id}
ORDER BY pp.created_at DESC, pp.id DESC
LIMIT 5;
ROLLBACK;
"""
        post_rows = db_sql(posts_sql)
        for pr in post_rows:
            p_author_raw = pr[2] or (pr[3].split("@")[0] if pr[3] else "Peer")
            pod_highlights.append({
                "post_id": int(pr[0]),
                "author": p_author_raw,
                "is_self": (int(pr[1]) == student_id),
                "week_number": int(pr[4]),
                "shipped": pr[5],
                "broke": pr[6],
                "next": pr[7],
            })

    if not pod_highlights:
        pod_highlights.append({
            "post_id": 0,
            "author": "Keel Dispatch",
            "is_self": False,
            "week_number": 1,
            "shipped": "New interactive workbench harnesses and calibrated diagnostic placement.",
            "broke": "Initial sandboxes hit memory limits on heavy property tests.",
            "next": "Peer review check-ins and weekly digest dispatches.",
        })

    pillar_pod_activity = {
        "has_pod": bool(pod_id),
        "pod_id": pod_id,
        "pod_name": pod_name,
        "highlights": pod_highlights,
        "summary": f"{len(pod_highlights)} check-ins shared in {pod_name} this week.",
    }

    # Pillar 4: Rebate & Streak Status
    rebate_sql = f"""BEGIN;
SELECT gate_id, unit_id, amount_cents, currency, rebate_pct, status,
       pledged_at::text, window_ends_at::text, earned_at::text
FROM rebates
WHERE student_id = {student_id}
ORDER BY id ASC;
ROLLBACK;
"""
    reb_rows = db_sql(rebate_sql)
    rebates_list = []
    earned_cents = 0
    pledged_cents = 0

    for rr in reb_rows:
        amt = int(rr[2])
        st = rr[5]
        pledged_cents += amt
        if st in ("earned", "paid"):
            earned_cents += amt
        rebates_list.append({
            "gate_id": rr[0],
            "unit_id": rr[1],
            "amount_cents": amt,
            "currency": rr[3],
            "status": st,
            "window_ends_at": rr[7],
            "earned_at": rr[8],
        })

    if not rebates_list:
        # Standard default rebate milestones
        rebates_list = [
            {
                "gate_id": "phase-5-integration",
                "unit_id": "5.1",
                "amount_cents": 30000,
                "currency": "usd",
                "status": "pending",
                "window_ends_at": (ref_dt.isoformat()),
                "earned_at": None,
            },
            {
                "gate_id": "capstone",
                "unit_id": "12.1",
                "amount_cents": 30000,
                "currency": "usd",
                "status": "pending",
                "window_ends_at": (ref_dt.isoformat()),
                "earned_at": None,
            },
        ]
        pledged_cents = 60000

    pillar_rebate_status = {
        "earned_cents": earned_cents,
        "pledged_cents": pledged_cents,
        "currency": "usd",
        "milestones": rebates_list,
        "summary": f"${earned_cents // 100} earned of ${pledged_cents // 100} pledged completion rebate (15% per gate).",
    }

    content_json = {
        "student_id": student_id,
        "display_name": display_name,
        "email": email,
        "cohort_week": effective_week,
        "generated_at": ref_dt.isoformat(),
        "pillars": {
            "current_location": pillar_current_location,
            "next_unlocks": pillar_next_unlocks,
            "pod_activity": pillar_pod_activity,
            "rebate_status": pillar_rebate_status,
        },
    }

    return content_json


def render_digest_email_text(digest_json: dict[str, Any]) -> str:
    """Render plain-text email representation of the personalized weekly digest."""
    name = digest_json.get("display_name", "Student")
    week = digest_json.get("cohort_week", "Weekly")
    pillars = digest_json.get("pillars", {})
    
    loc = pillars.get("current_location", {})
    unlocks = pillars.get("next_unlocks", {})
    pod = pillars.get("pod_activity", {})
    rebate = pillars.get("rebate_status", {})

    lines = [
        f"KEEL ACADEMY — WEEKLY PERSONALIZED DISPATCH ({week})",
        f"Hello {name}, here is where you stand and what unlocks next on your engineering flight path.\n",
        "============================================================",
        "1. CURRENT LOCATION & ACTIVE BENCH",
        "============================================================",
        f"• Active Unit: Unit {loc.get('active_unit')} — {loc.get('active_unit_title')}",
        f"• Status: {loc.get('current_route_step')}",
        f"• Completed Units: {len(loc.get('completed_units', []))} units cleared",
        f"• Note: {loc.get('note')}\n",
        "============================================================",
        "2. WHAT UNLOCKS NEXT",
        "============================================================",
        f"• Next Target Phase: Phase {unlocks.get('next_phase', 1)}",
    ]
    for u in unlocks.get("next_units", []):
        lines.append(f"  - Unit {u.get('unit_id')}: {u.get('title')} ({u.get('description')})")
    lines.append(f"• Summary: {unlocks.get('summary')}\n")

    lines.extend([
        "============================================================",
        f"3. POD ACCOUNTABILITY ACTIVITY — {pod.get('pod_name')}",
        "============================================================",
    ])
    for h in pod.get("highlights", []):
        lines.append(f"• {h.get('author')} (Week {h.get('week_number')}):")
        lines.append(f"  - Shipped: {h.get('shipped')}")
        lines.append(f"  - Broke: {h.get('broke')}")
        lines.append(f"  - Next: {h.get('next')}")
    lines.append(f"• {pod.get('summary')}\n")

    lines.extend([
        "============================================================",
        "4. REBATE LEDGER & DEADLINE TIMERS",
        "============================================================",
        f"• Total Earned: ${rebate.get('earned_cents', 0) // 100} / ${rebate.get('pledged_cents', 60000) // 100}",
    ])
    for m in rebate.get("milestones", []):
        lines.append(f"  - {m.get('gate_id')}: ${m.get('amount_cents', 0) // 100} [{m.get('status').upper()}]")
    lines.append(f"• Summary: {rebate.get('summary')}\n")

    lines.append("Open your dashboard: https://keel.academy/me\n")
    return "\n".join(lines)


def render_digest_email_html(digest_json: dict[str, Any]) -> str:
    """Render clean, responsive HTML email representation of the 4 pillars."""
    name = digest_json.get("display_name", "Student")
    week = digest_json.get("cohort_week", "Weekly")
    pillars = digest_json.get("pillars", {})
    
    loc = pillars.get("current_location", {})
    unlocks = pillars.get("next_unlocks", {})
    pod = pillars.get("pod_activity", {})
    rebate = pillars.get("rebate_status", {})

    unlocks_html = "".join(
        f'<li style="margin-bottom: 6px;"><strong>Unit {u.get("unit_id")}</strong>: {u.get("title")} <span style="color: #a1a1aa;">({u.get("description")})</span></li>'
        for u in unlocks.get("next_units", [])
    )

    pod_html = "".join(
        f'<div style="background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 12px; margin-bottom: 10px;">'
        f'<div style="font-weight: 600; color: #10b981; font-size: 13px; margin-bottom: 6px;">{h.get("author")} (Week {h.get("week_number")})</div>'
        f'<div style="font-size: 12px; color: #e4e4e7; margin-bottom: 4px;"><strong>Shipped:</strong> {h.get("shipped")}</div>'
        f'<div style="font-size: 12px; color: #f87171; margin-bottom: 4px;"><strong>Broke:</strong> {h.get("broke")}</div>'
        f'<div style="font-size: 12px; color: #38bdf8;"><strong>Next:</strong> {h.get("next")}</div>'
        f'</div>'
        for h in pod.get("highlights", [])
    )

    rebate_html = "".join(
        f'<div style="display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px solid #27272a;">'
        f'<span style="color: #e4e4e7;">{m.get("gate_id")}</span>'
        f'<span style="font-weight: 600; color: #10b981;">${m.get("amount_cents", 0) // 100} ({m.get("status").upper()})</span>'
        f'</div>'
        for m in rebate.get("milestones", [])
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Keel Academy Weekly Dispatch</title>
</head>
<body style="background-color: #09090b; color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 24px 12px; margin: 0;">
<table align="center" width="100%" style="max-width: 600px; background-color: #121215; border: 1px solid #27272a; border-radius: 8px; overflow: hidden; padding: 24px;">
  <tr>
    <td>
      <div style="font-family: monospace; font-size: 11px; font-weight: 700; color: #10b981; letter-spacing: 0.05em; text-transform: uppercase;">
        • KEEL ACADEMY WEEKLY DISPATCH ({week})
      </div>
      <h1 style="font-size: 22px; font-weight: 700; color: #fafafa; margin: 8px 0 16px 0;">
        Engineering Progress & Next Unlocks
      </h1>
      <p style="font-size: 14px; color: #a1a1aa; line-height: 1.5; margin-bottom: 24px;">
        Hello {name}, here is your proactive retention summary across the 4 pillars.
      </p>

      <!-- Pillar 1 -->
      <div style="background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 16px; margin-bottom: 16px;">
        <div style="font-family: monospace; font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase; margin-bottom: 4px;">
          1. Current Location
        </div>
        <div style="font-size: 16px; font-weight: 600; color: #fafafa;">
          Unit {loc.get('active_unit')} — {loc.get('active_unit_title')}
        </div>
        <p style="font-size: 13px; color: #d4d4d8; margin: 6px 0 0 0;">
          {loc.get('note')}
        </p>
      </div>

      <!-- Pillar 2 -->
      <div style="background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 16px; margin-bottom: 16px;">
        <div style="font-family: monospace; font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase; margin-bottom: 4px;">
          2. What Unlocks Next
        </div>
        <ul style="padding-left: 20px; font-size: 13px; color: #e4e4e7; margin: 8px 0;">
          {unlocks_html}
        </ul>
        <div style="font-size: 12px; color: #a1a1aa;">
          {unlocks.get('summary')}
        </div>
      </div>

      <!-- Pillar 3 -->
      <div style="background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 16px; margin-bottom: 16px;">
        <div style="font-family: monospace; font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase; margin-bottom: 8px;">
          3. Pod Activity — {pod.get('pod_name')}
        </div>
        {pod_html}
        <div style="font-size: 12px; color: #a1a1aa; margin-top: 8px;">
          {pod.get('summary')}
        </div>
      </div>

      <!-- Pillar 4 -->
      <div style="background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
        <div style="font-family: monospace; font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase; margin-bottom: 8px;">
          4. Completion Rebate Status
        </div>
        {rebate_html}
        <div style="font-size: 12px; color: #10b981; font-weight: 600; margin-top: 8px;">
          {rebate.get('summary')}
        </div>
      </div>

      <div style="text-align: center; margin-top: 16px;">
        <a href="https://keel.academy/me" style="background-color: #10b981; color: #09090b; font-size: 14px; font-weight: 700; text-decoration: none; padding: 12px 24px; border-radius: 6px; display: inline-block;">
          Open Your Dashboard &rarr;
        </a>
      </div>
    </td>
  </tr>
</table>
</body>
</html>
"""


def generate_and_deliver_student_digest(
    student_id: int,
    cohort_week: str | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Generate and deliver weekly personalized digest for student_id with deduplication.
    
    1. Idempotency check: If digest already exists for (student_id, cohort_week), returns existing record.
    2. Synthesizes 4-pillar payload.
    3. Persists digest row and emits 'digest.generated' spine event.
    4. Delivers via email transport.
    5. Updates delivered_at and emits 'digest.delivered' spine event.
    """
    effective_week = cohort_week or current_cohort_week(now_override)
    created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"

    # 1. Deduplication check
    chk_sql = f"""BEGIN;
SELECT id, student_id, cohort_week, content_json::text, email_to, delivered_at::text, created_at::text
FROM digests
WHERE student_id = {student_id} AND cohort_week = {sql_str(effective_week)}
LIMIT 1;
ROLLBACK;
"""
    existing = db_sql(chk_sql)
    if existing:
        row = existing[0]
        return {
            "id": int(row[0]),
            "student_id": int(row[1]),
            "cohort_week": row[2],
            "content_json": json.loads(row[3]),
            "email_to": row[4],
            "delivered_at": str(row[5]) if row[5] else None,
            "created_at": str(row[6]),
            "already_delivered": bool(row[5]),
            "newly_generated": False,
        }

    # 2. Synthesize 4 pillars
    digest_payload = synthesize_student_digest(
        student_id=student_id,
        cohort_week=effective_week,
        now_override=now_override,
    )
    email_to = digest_payload.get("email") or ""

    # 3. Persist digest row + emit 'digest.generated' spine event atomically
    content_str = sql_str(json.dumps(digest_payload))
    persist_sql = f"""BEGIN;
WITH d AS (
    INSERT INTO digests (student_id, cohort_week, content_json, email_to, created_at)
    VALUES ({student_id}, {sql_str(effective_week)}, {content_str}::jsonb, {sql_str(email_to)}, {created_at_sql})
    ON CONFLICT (student_id, cohort_week) DO NOTHING
    RETURNING id, student_id, cohort_week, content_json, email_to, created_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'digest.generated',
           jsonb_build_object(
               'digest_id', id,
               'student_id', student_id,
               'cohort_week', cohort_week,
               'email_to', email_to
           )
    FROM d
    RETURNING id
)
SELECT id, created_at::text FROM d;
COMMIT;
"""
    p_rows = db_sql(persist_sql)
    if not p_rows:
        # Race condition hit; fetch existing
        ex_rows = db_sql(chk_sql)
        if ex_rows:
            r = ex_rows[0]
            return {
                "id": int(r[0]),
                "student_id": int(r[1]),
                "cohort_week": r[2],
                "content_json": json.loads(r[3]),
                "email_to": r[4],
                "delivered_at": str(r[5]) if r[5] else None,
                "created_at": str(r[6]),
                "already_delivered": bool(r[5]),
                "newly_generated": False,
            }
        raise RuntimeError("failed_to_persist_digest")

    digest_id = int(p_rows[0][0])
    created_at_val = str(p_rows[0][1])

    # 4. Render and deliver email
    text_content = render_digest_email_text(digest_payload)
    html_content = render_digest_email_html(digest_payload)
    subject = f"Keel Academy Weekly Dispatch ({effective_week}) — {digest_payload.get('display_name')}"

    delivery_res = deliver_email(
        to_email=email_to,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )

    # 5. Mark delivered & emit 'digest.delivered' spine event atomically
    delivered_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"
    deliv_sql = f"""BEGIN;
WITH upd AS (
    UPDATE digests
    SET delivered_at = {delivered_at_sql}
    WHERE id = {digest_id} AND delivered_at IS NULL
    RETURNING id, student_id, cohort_week, email_to, delivered_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'digest.delivered',
           jsonb_build_object(
               'digest_id', id,
               'student_id', student_id,
               'cohort_week', cohort_week,
               'email_to', email_to,
               'delivery_id', {sql_str(str(delivery_res.get('delivery_id', 'delivered')))}
           )
    FROM upd
    RETURNING id
)
SELECT delivered_at::text FROM upd;
COMMIT;
"""
    deliv_rows = db_sql(deliv_sql)
    delivered_at_val = str(deliv_rows[0][0]) if deliv_rows else created_at_val

    return {
        "id": digest_id,
        "student_id": student_id,
        "cohort_week": effective_week,
        "content_json": digest_payload,
        "email_to": email_to,
        "delivered_at": delivered_at_val,
        "created_at": created_at_val,
        "already_delivered": False,
        "newly_generated": True,
    }


def get_latest_student_digest(student_id: int) -> dict[str, Any] | None:
    """Retrieve the most recent generated digest for a student."""
    sql = f"""BEGIN;
SELECT id, student_id, cohort_week, content_json::text, email_to, delivered_at::text, created_at::text
FROM digests
WHERE student_id = {student_id}
ORDER BY id DESC
LIMIT 1;
ROLLBACK;
"""
    rows = db_sql(sql)
    if not rows:
        return None
    r = rows[0]
    return {
        "id": int(r[0]),
        "student_id": int(r[1]),
        "cohort_week": r[2],
        "content_json": json.loads(r[3]),
        "email_to": r[4],
        "delivered_at": str(r[5]) if r[5] else None,
        "created_at": str(r[6]),
    }
