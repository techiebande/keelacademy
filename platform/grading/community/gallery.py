#!/usr/bin/env python3
"""community/gallery.py — public build gallery v1 and portfolio showcase engine (S4.4).

Encapsulates:
- Publishing verification & integrity gating: only passing submissions (verdicts.overall = 'pass')
  belonging to the student can be published. Unverified or failing submissions are strictly rejected (422).
- Ownership enforcement: student cannot publish or unpublish another student's submission / project (403).
- Gallery project upsert and unpublish state transitions.
- Atomic spine events emission ('gallery.published', 'gallery.unpublished').
- Public gallery listing with phase and unit filtering, search, and pagination.
- Full project detail retrieval with verified rubric proof and badge data.

Stdlib only.
"""

from __future__ import annotations

import json
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


def get_unit_title(unit_id: str) -> str:
    """Derive human-readable unit title from curriculum phases.yaml if available."""
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
    return f"Unit {unit_id}"


def publish_gallery_project(
    student_id: int,
    submission_id: int,
    title: str,
    description: str,
    repo_url: str | None = None,
    demo_url: str | None = None,
    walkthrough_video_url: str | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Publish a student portfolio project to the public build gallery.

    Integrity Rules:
    1. student_id exists.
    2. submission_id exists and belongs to student_id. Mismatch -> PermissionError(403).
    3. submission has a verified PASSING verdict (verdicts.overall = 'pass').
       Failing or unverified submissions are rejected -> ValueError('submission_not_eligible_for_gallery').
    4. Upserts gallery_projects (UNIQUE on student_id, unit_id) and sets published = true.
    5. Emits 'gallery.published' spine event atomically.
    """
    if student_id <= 0:
        raise ValueError("invalid_student_id")
    if submission_id <= 0:
        raise ValueError("invalid_submission_id")
    if not title or not title.strip():
        raise ValueError("title_required")
    if not description or not description.strip():
        raise ValueError("description_required")

    clean_title = title.strip()[:300]
    clean_desc = description.strip()
    clean_repo = repo_url.strip() if repo_url and repo_url.strip() else None
    clean_demo = demo_url.strip() if demo_url and demo_url.strip() else None
    clean_video = walkthrough_video_url.strip() if walkthrough_video_url and walkthrough_video_url.strip() else None

    # 1. Verify student exists
    st_rows = db_sql(f"BEGIN; SELECT id, display_name, email FROM students WHERE id = {student_id}; ROLLBACK;")
    if not st_rows:
        raise KeyError("student_not_found")

    # 2. Check submission existence, ownership, and verdict status
    sub_sql = f"""BEGIN;
SELECT s.id, s.student_id, s.unit_id, s.status, s.commit_sha, s.repo_url, v.overall, v.rubric_id, v.verdict_json::text
FROM submissions s
LEFT JOIN verdicts v ON v.submission_id = s.id
WHERE s.id = {submission_id};
ROLLBACK;
"""
    sub_rows = db_sql(sub_sql)
    if not sub_rows:
        raise ValueError("submission_not_found")

    sub_row = sub_rows[0]
    sub_owner_id = int(sub_row[1])
    unit_id = str(sub_row[2])
    sub_status = str(sub_row[3])
    commit_sha = str(sub_row[4])
    default_sub_repo = str(sub_row[5]) if sub_row[5] else None
    verdict_overall = str(sub_row[6]) if sub_row[6] else None
    rubric_id = str(sub_row[7]) if sub_row[7] else None

    # Enforce ownership boundary
    if sub_owner_id != student_id:
        raise PermissionError("submission_ownership_mismatch")

    # Enforce integrity rule: MUST have a passing verdict
    if verdict_overall != "pass":
        raise ValueError("submission_not_eligible_for_gallery")

    # Fall back to submission repo_url if no repo_url provided
    final_repo_url = clean_repo or default_sub_repo

    created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"

    # 3. Upsert gallery_projects record and emit atomic spine event
    persist_sql = f"""BEGIN;
WITH proj AS (
    INSERT INTO gallery_projects (
        student_id, unit_id, submission_id, title, description,
        repo_url, demo_url, walkthrough_video_url, published, created_at, updated_at
    ) VALUES (
        {student_id}, {sql_str(unit_id)}, {submission_id}, {sql_str(clean_title)}, {sql_str(clean_desc)},
        {sql_str(final_repo_url) if final_repo_url else "NULL"},
        {sql_str(clean_demo) if clean_demo else "NULL"},
        {sql_str(clean_video) if clean_video else "NULL"},
        true, {created_at_sql}, {created_at_sql}
    )
    ON CONFLICT (student_id, unit_id) DO UPDATE SET
        submission_id = EXCLUDED.submission_id,
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        repo_url = EXCLUDED.repo_url,
        demo_url = EXCLUDED.demo_url,
        walkthrough_video_url = EXCLUDED.walkthrough_video_url,
        published = true,
        updated_at = {created_at_sql}
    RETURNING id, student_id, unit_id, submission_id, title, description, repo_url, demo_url, walkthrough_video_url, published, created_at::text, updated_at::text
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'gallery.published',
           jsonb_build_object(
               'project_id', id,
               'student_id', student_id,
               'unit_id', unit_id,
               'submission_id', submission_id,
               'title', title
           )
    FROM proj
    RETURNING id
)
SELECT id, student_id, unit_id, submission_id, title, description, repo_url, demo_url, walkthrough_video_url, published, created_at, updated_at
FROM proj;
COMMIT;
"""
    p_rows = db_sql(persist_sql)
    if not p_rows:
        raise RuntimeError("failed_to_persist_gallery_project")

    r = p_rows[0]
    return {
        "ok": True,
        "id": int(r[0]),
        "student_id": int(r[1]),
        "unit_id": str(r[2]),
        "submission_id": int(r[3]),
        "title": str(r[4]),
        "description": str(r[5]),
        "repo_url": str(r[6]) if r[6] else None,
        "demo_url": str(r[7]) if r[7] else None,
        "walkthrough_video_url": str(r[8]) if r[8] else None,
        "published": (r[9] == "t" or r[9] is True),
        "created_at": str(r[10]),
        "updated_at": str(r[11]),
    }


def unpublish_gallery_project(
    student_id: int,
    project_id: int | None = None,
    unit_id: str | None = None,
    now_override: datetime | None = None,
) -> dict[str, Any]:
    """Unpublish a gallery project (sets published = false and logs gallery.unpublished)."""
    if student_id <= 0:
        raise ValueError("invalid_student_id")
    if project_id is None and unit_id is None:
        raise ValueError("project_id_or_unit_id_required")

    # 1. Lookup project
    if project_id is not None:
        chk_sql = f"BEGIN; SELECT id, student_id, unit_id, published FROM gallery_projects WHERE id = {project_id}; ROLLBACK;"
    else:
        chk_sql = f"BEGIN; SELECT id, student_id, unit_id, published FROM gallery_projects WHERE student_id = {student_id} AND unit_id = {sql_str(unit_id)}; ROLLBACK;"

    rows = db_sql(chk_sql)
    if not rows:
        raise KeyError("project_not_found")

    p_id = int(rows[0][0])
    p_owner_id = int(rows[0][1])
    p_unit_id = str(rows[0][2])

    if p_owner_id != student_id:
        raise PermissionError("project_ownership_mismatch")

    created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "clock_timestamp()"

    # 2. Atomic unpublish and event logging
    unpub_sql = f"""BEGIN;
WITH upd AS (
    UPDATE gallery_projects
    SET published = false, updated_at = {created_at_sql}
    WHERE id = {p_id}
    RETURNING id, student_id, unit_id, published, updated_at::text
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'gallery.unpublished',
           jsonb_build_object(
               'project_id', id,
               'student_id', student_id,
               'unit_id', unit_id
           )
    FROM upd
    RETURNING id
)
SELECT id, student_id, unit_id, published, updated_at FROM upd;
COMMIT;
"""
    u_rows = db_sql(unpub_sql)
    if not u_rows:
        raise RuntimeError("failed_to_unpublish_gallery_project")

    return {
        "ok": True,
        "project_id": p_id,
        "student_id": student_id,
        "unit_id": p_unit_id,
        "published": False,
        "updated_at": str(u_rows[0][4]),
    }


def list_gallery_projects(
    unit_id: str | None = None,
    phase: int | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Retrieve public published gallery projects with optional filters and pagination."""
    limit_clean = max(1, min(100, limit))
    offset_clean = max(0, offset)

    clauses = ["gp.published = true"]
    if unit_id:
        clauses.append(f"gp.unit_id = {sql_str(unit_id.strip())}")
    if phase is not None:
        clauses.append(f"split_part(gp.unit_id, '.', 1) = {sql_str(str(phase))}")
    if search and search.strip():
        q_clean = search.strip()
        clauses.append(f"(gp.title ILIKE {sql_str(f'%{q_clean}%')} OR gp.description ILIKE {sql_str(f'%{q_clean}%')} OR s.display_name ILIKE {sql_str(f'%{q_clean}%')})")

    where_clause = " AND ".join(clauses)

    sql = f"""BEGIN;
SELECT gp.id, gp.student_id, coalesce(s.display_name, split_part(s.email, '@', 1)),
       gp.unit_id, gp.submission_id, sub.commit_sha,
       gp.title, gp.description, gp.repo_url, gp.demo_url, gp.walkthrough_video_url,
       gp.published, gp.created_at::text, gp.updated_at::text,
       v.overall, v.rubric_id, v.verdict_json::text,
       count(*) OVER() as total_count
FROM gallery_projects gp
JOIN students s ON s.id = gp.student_id
JOIN submissions sub ON sub.id = gp.submission_id
LEFT JOIN verdicts v ON v.submission_id = sub.id
WHERE {where_clause}
ORDER BY gp.created_at DESC, gp.id DESC
LIMIT {limit_clean} OFFSET {offset_clean};
ROLLBACK;
"""
    rows = db_sql(sql)
    projects = []
    total = 0

    for r in rows:
        total = int(r[17])
        pid = int(r[0])
        sid = int(r[1])
        st_name = str(r[2])
        uid = str(r[3])
        sub_id = int(r[4])
        commit_sha = str(r[5])
        title = str(r[6])
        description = str(r[7])
        repo_url = str(r[8]) if r[8] else None
        demo_url = str(r[9]) if r[9] else None
        video_url = str(r[10]) if r[10] else None
        pub = (r[11] == "t" or r[11] is True)
        created_at = str(r[12])
        updated_at = str(r[13])
        v_overall = str(r[14]) if r[14] else "pass"
        v_rubric_id = str(r[15]) if r[15] else None
        v_json_raw = str(r[16]) if r[16] else "{}"

        # Derive phase
        try:
            p_num = int(uid.split(".")[0])
        except (ValueError, IndexError):
            p_num = 0

        # Parse verdict summary badge
        criteria_passed = 0
        total_criteria = 0
        try:
            v_data = json.loads(v_json_raw)
            judge_data = v_data.get("judge") or {}
            crit_list = judge_data.get("criteria") or []
            total_criteria = len(crit_list)
            criteria_passed = sum(1 for c in crit_list if c.get("verdict") == "pass")
        except Exception:
            pass

        projects.append({
            "id": pid,
            "student_id": sid,
            "student_name": st_name,
            "unit_id": uid,
            "unit_title": get_unit_title(uid),
            "phase": p_num,
            "submission_id": sub_id,
            "commit_sha": commit_sha,
            "title": title,
            "description": description,
            "repo_url": repo_url,
            "demo_url": demo_url,
            "walkthrough_video_url": video_url,
            "published": pub,
            "created_at": created_at,
            "updated_at": updated_at,
            "verdict": {
                "overall": v_overall,
                "rubric_id": v_rubric_id,
                "criteria_passed": criteria_passed,
                "total_criteria": total_criteria,
            },
        })

    return {
        "projects": projects,
        "total": total,
        "limit": limit_clean,
        "offset": offset_clean,
    }


def get_gallery_project(project_id: int) -> dict[str, Any] | None:
    """Retrieve full detail for a single gallery project including verification proof."""
    sql = f"""BEGIN;
SELECT gp.id, gp.student_id, coalesce(s.display_name, split_part(s.email, '@', 1)),
       gp.unit_id, gp.submission_id, sub.commit_sha, sub.repo_url,
       gp.title, gp.description, gp.repo_url, gp.demo_url, gp.walkthrough_video_url,
       gp.published, gp.created_at::text, gp.updated_at::text,
       v.overall, v.rubric_id, v.rubric_version, v.verdict_json::text, v.issued_at::text
FROM gallery_projects gp
JOIN students s ON s.id = gp.student_id
JOIN submissions sub ON sub.id = gp.submission_id
LEFT JOIN verdicts v ON v.submission_id = sub.id
WHERE gp.id = {project_id};
ROLLBACK;
"""
    rows = db_sql(sql)
    if not rows:
        return None

    r = rows[0]
    pid = int(r[0])
    sid = int(r[1])
    st_name = str(r[2])
    uid = str(r[3])
    sub_id = int(r[4])
    commit_sha = str(r[5])
    sub_repo = str(r[6]) if r[6] else None
    title = str(r[7])
    description = str(r[8])
    repo_url = str(r[9]) if r[9] else sub_repo
    demo_url = str(r[10]) if r[10] else None
    video_url = str(r[11]) if r[11] else None
    published = (r[12] == "t" or r[12] is True)
    created_at = str(r[13])
    updated_at = str(r[14])
    v_overall = str(r[15]) if r[15] else "pass"
    v_rubric_id = str(r[16]) if r[16] else None
    v_rubric_ver = int(r[17]) if r[17] and r[17].isdigit() else None
    v_json_raw = str(r[18]) if r[18] else "{}"
    v_issued_at = str(r[19]) if r[19] else None

    try:
        p_num = int(uid.split(".")[0])
    except (ValueError, IndexError):
        p_num = 0

    verdict_json = {}
    try:
        verdict_json = json.loads(v_json_raw)
    except Exception:
        pass

    return {
        "id": pid,
        "student_id": sid,
        "student_name": st_name,
        "unit_id": uid,
        "unit_title": get_unit_title(uid),
        "phase": p_num,
        "submission_id": sub_id,
        "commit_sha": commit_sha,
        "title": title,
        "description": description,
        "repo_url": repo_url,
        "demo_url": demo_url,
        "walkthrough_video_url": video_url,
        "published": published,
        "created_at": created_at,
        "updated_at": updated_at,
        "verdict": {
            "overall": v_overall,
            "rubric_id": v_rubric_id,
            "rubric_version": v_rubric_ver,
            "issued_at": v_issued_at,
            "json": verdict_json,
        },
    }


def get_student_gallery_projects(student_id: int) -> list[dict[str, Any]]:
    """Retrieve all gallery project records (published and unpublished) for a student."""
    sql = f"""BEGIN;
SELECT gp.id, gp.student_id, gp.unit_id, gp.submission_id, sub.commit_sha,
       gp.title, gp.description, gp.repo_url, gp.demo_url, gp.walkthrough_video_url,
       gp.published, gp.created_at::text, gp.updated_at::text,
       v.overall, v.rubric_id
FROM gallery_projects gp
JOIN submissions sub ON sub.id = gp.submission_id
LEFT JOIN verdicts v ON v.submission_id = sub.id
WHERE gp.student_id = {student_id}
ORDER BY gp.created_at DESC, gp.id DESC;
ROLLBACK;
"""
    rows = db_sql(sql)
    projects = []
    for r in rows:
        uid = str(r[2])
        try:
            p_num = int(uid.split(".")[0])
        except (ValueError, IndexError):
            p_num = 0
        projects.append({
            "id": int(r[0]),
            "student_id": int(r[1]),
            "unit_id": uid,
            "unit_title": get_unit_title(uid),
            "phase": p_num,
            "submission_id": int(r[3]),
            "commit_sha": str(r[4]),
            "title": str(r[5]),
            "description": str(r[6]),
            "repo_url": str(r[7]) if r[7] else None,
            "demo_url": str(r[8]) if r[8] else None,
            "walkthrough_video_url": str(r[9]) if r[9] else None,
            "published": (r[10] == "t" or r[10] is True),
            "created_at": str(r[11]),
            "updated_at": str(r[12]),
            "overall": str(r[13]) if r[13] else "pass",
            "rubric_id": str(r[14]) if r[14] else None,
        })
    return projects


def get_submission_gallery_project(submission_id: int) -> dict[str, Any] | None:
    """Retrieve gallery entry associated with a specific submission_id."""
    sql = f"""BEGIN;
SELECT gp.id, gp.student_id, gp.unit_id, gp.submission_id,
       gp.title, gp.description, gp.repo_url, gp.demo_url, gp.walkthrough_video_url,
       gp.published, gp.created_at::text, gp.updated_at::text
FROM gallery_projects gp
WHERE gp.submission_id = {submission_id};
ROLLBACK;
"""
    rows = db_sql(sql)
    if not rows:
        return None
    r = rows[0]
    return {
        "id": int(r[0]),
        "student_id": int(r[1]),
        "unit_id": str(r[2]),
        "submission_id": int(r[3]),
        "title": str(r[4]),
        "description": str(r[5]),
        "repo_url": str(r[6]) if r[6] else None,
        "demo_url": str(r[7]) if r[7] else None,
        "walkthrough_video_url": str(r[8]) if r[8] else None,
        "published": (r[9] == "t" or r[9] is True),
        "created_at": str(r[10]),
        "updated_at": str(r[11]),
    }
