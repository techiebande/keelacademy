#!/usr/bin/env python3
"""community/pods.py — pod allocation, weekly post submission, and retrieval engine (S4.2).

Encapsulates:
- Cohort week calculation (ISO format YYYY-Www)
- Pod capacity enforcement (target 6-10 students, fills up to 10 then spawns new pod)
- Idempotent assignment
- Weekly post validation (3 mandatory pillars: shipped, broke, next) and uniqueness enforcement
- Spine event emission ('pod.assigned', 'pod.post_submitted')
- Deterministic Discord relay via community/discord.py

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import shared db module and discord client
GRADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str
from community.discord import relay_pod_post_to_discord

TARGET_MIN_POD_SIZE = 6
MAX_POD_CAPACITY = 10


def current_cohort_week(override_dt: datetime | None = None) -> str:
    """Derive cohort week string in ISO format e.g. 2026-W35."""
    dt = override_dt or datetime.now(timezone.utc)
    year, week, _ = dt.isocalendar()
    return f"{year:04d}-W{week:02d}"


def assign_student_to_pod(
    student_id: int,
    cohort_week: str | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Assign a student to a pod for their cohort week.
    
    1. Idempotency: If student is already in an active pod, returns existing membership.
    2. Capacity check: Finds the earliest created pod for this cohort week with < MAX_POD_CAPACITY (10) members.
    3. If none exists, provisions a new pod: 'Pod <cohort_week>-<seq>'.
    4. Inserts pod_memberships row and emits 'pod.assigned' spine event atomically.
    """
    effective_week = cohort_week or current_cohort_week(now_override)
    created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"

    # 1. Check existing active membership
    check_sql = f"""BEGIN;
SELECT p.id, p.name, p.cohort_week, p.discord_channel_id, p.discord_role_id, pm.joined_at::text
FROM pod_memberships pm
JOIN pods p ON p.id = pm.pod_id
WHERE pm.student_id = {student_id} AND pm.active = true
LIMIT 1;
ROLLBACK;
"""
    existing = db_sql(check_sql)
    if existing:
        r = existing[0]
        return {
            "pod_id": int(r[0]),
            "name": r[1],
            "cohort_week": r[2],
            "discord_channel_id": r[3] if r[3] else None,
            "discord_role_id": r[4] if r[4] else None,
            "joined_at": str(r[5]),
            "newly_assigned": False,
        }

    # 2. Check student existence
    st_check = db_sql(f"BEGIN; SELECT id, display_name, email FROM students WHERE id = {student_id}; ROLLBACK;")
    if not st_check:
        raise ValueError("student_not_found")

    # 3. Find available active pod for this cohort week (< 10 members)
    find_pod_sql = f"""BEGIN;
SELECT p.id, p.name, count(pm.student_id) as member_count
FROM pods p
LEFT JOIN pod_memberships pm ON pm.pod_id = p.id AND pm.active = true
WHERE p.cohort_week = {sql_str(effective_week)}
GROUP BY p.id, p.name
HAVING count(pm.student_id) < {MAX_POD_CAPACITY}
ORDER BY p.id ASC
LIMIT 1;
ROLLBACK;
"""
    avail_rows = db_sql(find_pod_sql)
    target_pod_id: int | None = None
    target_pod_name: str | None = None

    if avail_rows:
        target_pod_id = int(avail_rows[0][0])
        target_pod_name = avail_rows[0][1]
    else:
        # Count existing pods in this cohort week to name the new pod
        count_rows = db_sql(f"BEGIN; SELECT count(*) FROM pods WHERE cohort_week = {sql_str(effective_week)}; ROLLBACK;")
        cohort_pods_count = int(count_rows[0][0]) if count_rows else 0
        letter_suffix = chr(65 + (cohort_pods_count % 26))
        target_pod_name = f"Pod {effective_week}-{letter_suffix}"
        chan_id = f"chan_{effective_week}_{cohort_pods_count + 1}"
        role_id = f"role_{effective_week}"

        create_pod_sql = f"""BEGIN;
INSERT INTO pods (name, cohort_week, discord_channel_id, discord_role_id, created_at)
VALUES ({sql_str(target_pod_name)}, {sql_str(effective_week)}, {sql_str(chan_id)}, {sql_str(role_id)}, {created_at_sql})
RETURNING id, name, cohort_week, discord_channel_id, discord_role_id;
COMMIT;
"""
        created_rows = db_sql(create_pod_sql)
        target_pod_id = int(created_rows[0][0])
        target_pod_name = created_rows[0][1]

    # 4. Insert membership & emit spine event atomically
    assign_sql = f"""BEGIN;
WITH membership AS (
    INSERT INTO pod_memberships (pod_id, student_id, joined_at, active)
    VALUES ({target_pod_id}, {student_id}, {created_at_sql}, true)
    ON CONFLICT (pod_id, student_id) DO UPDATE SET active = true
    RETURNING pod_id, student_id, joined_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'pod.assigned',
           jsonb_build_object(
               'pod_id', m.pod_id,
               'student_id', m.student_id,
               'cohort_week', {sql_str(effective_week)},
               'pod_name', {sql_str(target_pod_name)}
           )
    FROM membership m
    RETURNING id
)
SELECT p.id, p.name, p.cohort_week, p.discord_channel_id, p.discord_role_id, m.joined_at::text
FROM membership m
JOIN pods p ON p.id = m.pod_id;
COMMIT;
"""
    rows = db_sql(assign_sql)
    if not rows:
        raise RuntimeError("failed_to_assign_pod")

    r = rows[0]
    return {
        "pod_id": int(r[0]),
        "name": r[1],
        "cohort_week": r[2],
        "discord_channel_id": r[3] if r[3] else None,
        "discord_role_id": r[4] if r[4] else None,
        "joined_at": str(r[5]),
        "newly_assigned": True,
    }


def get_student_pod_details(student_id: int) -> dict[str, Any] | None:
    """Retrieve the student's current active pod details, Discord deep link, and peer list."""
    sql = f"""BEGIN;
SELECT p.id, p.name, p.cohort_week, p.discord_channel_id, p.discord_role_id, pm.joined_at::text
FROM pod_memberships pm
JOIN pods p ON p.id = pm.pod_id
WHERE pm.student_id = {student_id} AND pm.active = true
LIMIT 1;

SELECT s.id, s.display_name, s.email, pm.joined_at::text
FROM pod_memberships pm
JOIN students s ON s.id = pm.student_id
WHERE pm.pod_id = (
    SELECT pod_id FROM pod_memberships WHERE student_id = {student_id} AND active = true LIMIT 1
) AND pm.active = true
ORDER BY pm.joined_at ASC;
ROLLBACK;
"""
    rows = db_sql(sql)
    if not rows:
        return None

    # First row is pod info
    p = rows[0]
    pod_id = int(p[0])
    pod_name = p[1]
    cohort_week = p[2]
    channel_id = p[3] if p[3] else None
    role_id = p[4] if p[4] else None
    joined_at = str(p[5])

    # Remaining rows are peers (filter by 4-column structure)
    peers = []
    for r in rows[1:]:
        if len(r) == 4:
            peer_id = int(r[0])
            name = r[1]
            email = r[2]
            peer_joined = str(r[3])
            display = name if name else email.split("@")[0]
            peers.append({
                "student_id": peer_id,
                "display_name": display,
                "is_self": peer_id == student_id,
                "joined_at": peer_joined,
            })

    discord_url = f"https://discord.com/channels/@me/{channel_id}" if channel_id else None

    return {
        "pod_id": pod_id,
        "name": pod_name,
        "cohort_week": cohort_week,
        "discord_channel_id": channel_id,
        "discord_role_id": role_id,
        "discord_channel_url": discord_url,
        "joined_at": joined_at,
        "peers": peers,
    }


def submit_pod_post(
    student_id: int,
    pod_id: int,
    week_number: int,
    shipped_text: str,
    broke_text: str,
    next_text: str,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Submit a weekly accountability post enforcing the 3 mandatory pillars.
    
    1. Validates presence and non-empty content for shipped, broke, and next text.
    2. Validates week_number >= 1.
    3. Validates student is an active member of pod_id.
    4. Enforces uniqueness per (pod_id, student_id, week_number).
    5. Relays to Discord adapter.
    6. Persists post and emits 'pod.post_submitted' spine event.
    """
    if not shipped_text or not shipped_text.strip():
        raise ValueError("shipped_text_required")
    if not broke_text or not broke_text.strip():
        raise ValueError("broke_text_required")
    if not next_text or not next_text.strip():
        raise ValueError("next_text_required")
    if week_number < 1:
        raise ValueError("invalid_week_number")

    # 1. Verify student membership in pod
    mem_sql = f"""BEGIN;
SELECT p.name, p.cohort_week, p.discord_channel_id, s.display_name, s.email
FROM pod_memberships pm
JOIN pods p ON p.id = pm.pod_id
JOIN students s ON s.id = pm.student_id
WHERE pm.pod_id = {pod_id} AND pm.student_id = {student_id} AND pm.active = true;
ROLLBACK;
"""
    m_rows = db_sql(mem_sql)
    if not m_rows:
        raise PermissionError("not_pod_member")

    pod_name, cohort_week, discord_chan, st_name, st_email = m_rows[0]
    display_name = st_name if st_name else st_email.split("@")[0]

    # 2. Check for duplicate post
    dup_sql = f"""BEGIN;
SELECT id FROM pod_posts WHERE pod_id = {pod_id} AND student_id = {student_id} AND week_number = {week_number};
ROLLBACK;
"""
    dup_rows = db_sql(dup_sql)
    if dup_rows:
        raise KeyError("post_already_submitted_for_week")

    # 3. Relay to Discord
    discord_msg_id = relay_pod_post_to_discord(
        student_name=display_name,
        pod_name=pod_name,
        cohort_week=cohort_week,
        week_number=week_number,
        shipped_text=shipped_text,
        broke_text=broke_text,
        next_text=next_text,
        discord_channel_id=discord_chan,
    )

    created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"

    # 4. Atomic persistence & event emission
    persist_sql = f"""BEGIN;
WITH post AS (
    INSERT INTO pod_posts (
        pod_id, student_id, week_number, shipped_text, broke_text, next_text, discord_message_id, created_at
    ) VALUES (
        {pod_id}, {student_id}, {week_number}, {sql_str(shipped_text.strip())},
        {sql_str(broke_text.strip())}, {sql_str(next_text.strip())},
        {sql_str(discord_msg_id) if discord_msg_id else "NULL"}, {created_at_sql}
    )
    RETURNING id, pod_id, student_id, week_number, shipped_text, broke_text, next_text, discord_message_id, created_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'pod.post_submitted',
           jsonb_build_object(
               'post_id', id,
               'pod_id', pod_id,
               'student_id', student_id,
               'week_number', week_number,
               'discord_message_id', discord_message_id
           )
    FROM post
    RETURNING id
)
SELECT id, created_at FROM post;
COMMIT;
"""
    p_rows = db_sql(persist_sql)
    if not p_rows:
        raise RuntimeError("failed_to_persist_post")

    post_id = int(p_rows[0][0])
    created_at_val = str(p_rows[0][1])

    return {
        "ok": True,
        "post_id": post_id,
        "pod_id": pod_id,
        "student_id": student_id,
        "week_number": week_number,
        "shipped_text": shipped_text.strip(),
        "broke_text": broke_text.strip(),
        "next_text": next_text.strip(),
        "discord_message_id": discord_msg_id,
        "created_at": created_at_val,
    }


def get_pod_posts(pod_id: int, week_number: int | None = None) -> list[dict[str, Any]]:
    """Retrieve all submitted weekly posts for a pod, optionally filtered by week_number."""
    week_clause = f"AND pp.week_number = {week_number}" if week_number is not None else ""
    sql = f"""BEGIN;
SELECT pp.id, pp.pod_id, pp.student_id, s.display_name, s.email, pp.week_number,
       pp.shipped_text, pp.broke_text, pp.next_text, pp.discord_message_id, pp.created_at::text
FROM pod_posts pp
JOIN students s ON s.id = pp.student_id
WHERE pp.pod_id = {pod_id} {week_clause}
ORDER BY pp.created_at DESC, pp.id DESC;
ROLLBACK;
"""
    rows = db_sql(sql)
    posts = []
    for r in rows:
        st_name = r[3]
        st_email = r[4]
        display = st_name if st_name else st_email.split("@")[0]
        posts.append({
            "id": int(r[0]),
            "pod_id": int(r[1]),
            "student_id": int(r[2]),
            "author_name": display,
            "week_number": int(r[5]),
            "shipped_text": r[6],
            "broke_text": r[7],
            "next_text": r[8],
            "discord_message_id": r[9] if r[9] else None,
            "created_at": str(r[10]),
        })
    return posts
