#!/usr/bin/env python3
"""smoke-gallery-checks.py — deterministic proof battery for Public Build Gallery v1 (S4.4).

Verifies:
1. Eligibility Gating & Integrity Rules:
   - 401 on missing or invalid app auth token.
   - 403 on publishing another student's submission (ownership boundary).
   - 422 on publishing a failing submission (verdicts.overall = 'fail').
   - 422 on publishing an unverified / queued submission (no verdict).
   - 404 on publishing non-existent submission or student.
2. Lifecycle & Opt-In:
   - Successful publish of passing submission (HTTP 200).
   - Project appears in public GET /gallery.
   - 403 on unpublishing another student's project.
   - Successful unpublish -> excluded from public listing.
   - Successful re-publish -> restored to public listing.
3. Multi-Project Publishing & Filtering:
   - Publishing projects across Phase 1, Phase 5, and Phase 12.
   - Phase filter (?phase=1, ?phase=5, ?phase=12, ?phase=2) returns exact project subsets.
   - Unit filter (?unit_id=1.1) returns exact project.
   - Search filter matches on title and description.
4. Detail View & Verification Proof:
   - GET /gallery/<id> returns rich showcase details with rubric badge and evidence quotes.
   - 404 on non-existent project id.
5. Spine Events & Student Queries:
   - Atomic logging of 'gallery.published' and 'gallery.unpublished' events on DB spine.
   - Per-student projects query (/students/<id>/gallery).
   - Per-submission gallery link query (/gallery/submission/<id>).

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
    print("== Running S4.4 Public Build Gallery Smoke Battery ==")

    # ------------------------------------------------------------------
    # 1. Eligibility Gating & Integrity Rules
    # ------------------------------------------------------------------
    print("\n-- 1. Testing Eligibility Gating & Integrity Rules --")

    # (a) Missing auth token on publish -> 401
    status, res = http_request(
        "/gallery/publish",
        method="POST",
        body={"student_id": 1, "submission_id": 1, "title": "Test", "description": "Test"},
        token=None,
    )
    if status == 401:
        record_pass("Publish without auth token rejected with 401 Unauthorized")
    else:
        record_fail("Publish without auth token should return 401", f"got {status}: {res}")

    # (b) Non-existent submission -> 404
    status, res = http_request(
        "/gallery/publish",
        method="POST",
        body={"student_id": 1, "submission_id": 999, "title": "Test", "description": "Test"},
    )
    if status == 404:
        record_pass("Publish with non-existent submission_id returns 404")
    else:
        record_fail("Publish non-existent submission should return 404", f"got {status}: {res}")

    # (c) Ownership boundary: Alice (student 1) tries to publish Bob's submission (sub 3) -> 403
    status, res = http_request(
        "/gallery/publish",
        method="POST",
        body={"student_id": 1, "submission_id": 3, "title": "Alice stolen Bob work", "description": "Test"},
    )
    if status == 403:
        record_pass("Publishing another student's submission rejected with 403 Forbidden")
    else:
        record_fail("Publishing other student's submission should return 403", f"got {status}: {res}")

    # (d) Failing submission: Alice's submission 2 (Unit 1.2, verdict = 'fail') -> 422
    status, res = http_request(
        "/gallery/publish",
        method="POST",
        body={"student_id": 1, "submission_id": 2, "title": "Failing project", "description": "Test"},
    )
    if status == 422 and "submission_not_eligible" in str(res):
        record_pass("Publishing failing submission (verdict != pass) rejected with 422")
    else:
        record_fail("Failing submission publication should return 422", f"got {status}: {res}")

    # (e) Queued submission without verdict: Alice's submission 5 (Unit 3.2.1, status = 'queued') -> 422
    status, res = http_request(
        "/gallery/publish",
        method="POST",
        body={"student_id": 1, "submission_id": 5, "title": "Queued project", "description": "Test"},
    )
    if status == 422 and "submission_not_eligible" in str(res):
        record_pass("Publishing unverified/queued submission rejected with 422")
    else:
        record_fail("Unverified submission publication should return 422", f"got {status}: {res}")

    # (f) Passing submission: Alice's submission 1 (Unit 1.1, verdict = 'pass') -> 200
    status, alice_proj = http_request(
        "/gallery/publish",
        method="POST",
        body={
            "student_id": 1,
            "submission_id": 1,
            "title": "Invoice Extraction & Pydantic Validation Pipeline",
            "description": "High-throughput claims parsing pipeline with automated schema validation and 100% test coverage.",
            "repo_url": "https://github.com/alice/unit1.1-final",
            "demo_url": "https://alice-claims.dev",
            "walkthrough_video_url": "https://loom.com/share/alice-claims-walkthrough",
        },
    )
    if status == 200 and alice_proj.get("id") and alice_proj.get("published") is True:
        record_pass("Publishing verified passing submission succeeds with 200 OK")
    else:
        record_fail("Passing submission should publish with 200", f"got {status}: {alice_proj}")

    alice_project_id = alice_proj.get("id")

    # ------------------------------------------------------------------
    # 2. Opt-In, Public Discoverability & Unpublish Lifecycle
    # ------------------------------------------------------------------
    print("\n-- 2. Testing Gallery Discoverability & Unpublish Lifecycle --")

    # (a) Public GET /gallery lists Alice's published project (public request without token)
    status, public_gallery = http_request("/gallery", method="GET", token=None)
    if status == 200 and public_gallery.get("total") == 1:
        record_pass("Public GET /gallery without token returns 200 with published project")
    else:
        record_fail("Public GET /gallery should return 1 project", f"got {status}: {public_gallery}")

    p0 = public_gallery.get("projects", [{}])[0]
    if p0.get("student_name") == "Alice Engineer" and p0.get("unit_id") == "1.1":
        record_pass("Gallery listing contains student display name and unit ID")
    else:
        record_fail("Project in gallery missing expected metadata", str(p0))

    if p0.get("verdict", {}).get("overall") == "pass":
        record_pass("Gallery listing includes verified rubric pass badge")
    else:
        record_fail("Project missing rubric verdict badge", str(p0))

    # (b) Unpublish authorization boundary: Bob (student 2) tries to unpublish Alice's project -> 403
    status, res = http_request(
        "/gallery/unpublish",
        method="POST",
        body={"student_id": 2, "project_id": alice_project_id},
    )
    if status == 403:
        record_pass("Unpublishing another student's project rejected with 403 Forbidden")
    else:
        record_fail("Unpublishing other student's project should return 403", f"got {status}: {res}")

    # (c) Alice unpublishes her project -> 200
    status, unpub_res = http_request(
        "/gallery/unpublish",
        method="POST",
        body={"student_id": 1, "project_id": alice_project_id},
    )
    if status == 200 and unpub_res.get("published") is False:
        record_pass("Owner unpublishing project succeeds with 200 OK")
    else:
        record_fail("Unpublish failed", f"got {status}: {unpub_res}")

    # (d) Verify project is excluded from public GET /gallery
    status, empty_gallery = http_request("/gallery", method="GET", token=None)
    if status == 200 and empty_gallery.get("total") == 0 and len(empty_gallery.get("projects", [])) == 0:
        record_pass("Unpublished project is excluded from public gallery listing (total=0)")
    else:
        record_fail("Unpublished project still visible in gallery", f"got {empty_gallery}")

    # (e) Re-publish Alice's project -> 200
    status, repub_res = http_request(
        "/gallery/publish",
        method="POST",
        body={
            "student_id": 1,
            "submission_id": 1,
            "title": "Invoice Extraction & Pydantic Validation Pipeline (v2)",
            "description": "Updated high-throughput claims parsing pipeline.",
            "repo_url": "https://github.com/alice/unit1.1-final",
        },
    )
    if status == 200 and repub_res.get("published") is True:
        record_pass("Re-publishing upserts existing record and restores published=true")
    else:
        record_fail("Re-publish failed", f"got {status}: {repub_res}")

    status, restored_gallery = http_request("/gallery", method="GET", token=None)
    if status == 200 and restored_gallery.get("total") == 1:
        record_pass("Project is restored to public gallery listing")
    else:
        record_fail("Restored gallery check failed", str(restored_gallery))

    # ------------------------------------------------------------------
    # 3. Multi-Project Publishing & Filtering
    # ------------------------------------------------------------------
    print("\n-- 3. Testing Multi-Project Publishing & Phase/Unit Filtering --")

    # Bob publishes Unit 5.1 (Phase 5)
    status, bob_proj = http_request(
        "/gallery/publish",
        method="POST",
        body={
            "student_id": 2,
            "submission_id": 3,
            "title": "Autonomous Multi-Tool Dispute Triage Agent",
            "description": "Multi-tool triage agent evaluating supplier entitlements and routing disputes to specialist queues.",
            "repo_url": "https://github.com/bob/agent-triage",
            "demo_url": "https://bob-triage.dev",
        },
    )
    if status == 200:
        record_pass("Bob successfully publishes Unit 5.1 (Phase 5) deliverable")
    else:
        record_fail("Bob publish failed", f"got {status}: {bob_proj}")
    bob_project_id = bob_proj.get("id")

    # Carol publishes Unit 12.1 (Phase 12 Capstone)
    status, carol_proj = http_request(
        "/gallery/publish",
        method="POST",
        body={
            "student_id": 3,
            "submission_id": 4,
            "title": "Production Dispute Operations Capstone Platform",
            "description": "Full end-to-end autonomous dispute resolution pipeline with human-in-the-loop escalation.",
            "repo_url": "https://github.com/carol/capstone-omnicart",
            "walkthrough_video_url": "https://youtube.com/watch?v=carol-capstone-demo",
        },
    )
    if status == 200:
        record_pass("Carol successfully publishes Unit 12.1 (Phase 12 Capstone) deliverable")
    else:
        record_fail("Carol publish failed", f"got {status}: {carol_proj}")
    carol_project_id = carol_proj.get("id")

    # Verify total published is now 3
    status, all_proj = http_request("/gallery", method="GET")
    if status == 200 and all_proj.get("total") == 3:
        record_pass("Total published gallery projects is 3")
    else:
        record_fail("Total published count should be 3", str(all_proj))

    # Test Phase 1 filter -> returns 1 project (Alice)
    status, p1 = http_request("/gallery?phase=1", method="GET")
    if status == 200 and p1.get("total") == 1 and p1.get("projects", [{}])[0].get("unit_id") == "1.1":
        record_pass("Filter ?phase=1 returns exact Phase 1 project subset")
    else:
        record_fail("Phase 1 filter failed", str(p1))

    # Test Phase 5 filter -> returns 1 project (Bob)
    status, p5 = http_request("/gallery?phase=5", method="GET")
    if status == 200 and p5.get("total") == 1 and p5.get("projects", [{}])[0].get("unit_id") == "5.1":
        record_pass("Filter ?phase=5 returns exact Phase 5 project subset")
    else:
        record_fail("Phase 5 filter failed", str(p5))

    # Test Phase 12 filter -> returns 1 project (Carol)
    status, p12 = http_request("/gallery?phase=12", method="GET")
    if status == 200 and p12.get("total") == 1 and p12.get("projects", [{}])[0].get("unit_id") == "12.1":
        record_pass("Filter ?phase=12 returns exact Capstone project subset")
    else:
        record_fail("Phase 12 filter failed", str(p12))

    # Test Phase 2 filter (empty) -> returns 0
    status, p2 = http_request("/gallery?phase=2", method="GET")
    if status == 200 and p2.get("total") == 0:
        record_pass("Filter ?phase=2 returns empty set when no projects in phase")
    else:
        record_fail("Phase 2 filter should return 0", str(p2))

    # Test Unit filter ?unit_id=1.1
    status, u1 = http_request("/gallery?unit_id=1.1", method="GET")
    if status == 200 and u1.get("total") == 1 and u1.get("projects", [{}])[0].get("unit_id") == "1.1":
        record_pass("Filter ?unit_id=1.1 returns exact unit project")
    else:
        record_fail("Unit 1.1 filter failed", str(u1))

    # Test Search filter ?search=Triage
    status, s_res = http_request("/gallery?search=Triage", method="GET")
    if status == 200 and s_res.get("total") == 1 and s_res.get("projects", [{}])[0].get("student_name") == "Bob Builder":
        record_pass("Search ?search=Triage correctly matches Bob's project")
    else:
        record_fail("Search filter failed", str(s_res))

    # ------------------------------------------------------------------
    # 4. Project Detail View & Verification Proof
    # ------------------------------------------------------------------
    print("\n-- 4. Testing Project Detail View & Verification Proof --")

    # (a) GET /gallery/<id> for Alice's project
    status, detail = http_request(f"/gallery/{alice_project_id}", method="GET", token=None)
    if status == 200 and detail.get("id") == alice_project_id:
        record_pass("GET /gallery/<id> returns 200 with full project detail")
    else:
        record_fail("GET /gallery/<id> failed", f"got {status}: {detail}")

    if detail.get("student_name") == "Alice Engineer" and detail.get("commit_sha") == "a1b2c3d4e5f6":
        record_pass("Project detail includes author and commit SHA")
    else:
        record_fail("Project detail missing author or commit", str(detail))

    verdict_info = detail.get("verdict", {})
    if verdict_info.get("overall") == "pass" and verdict_info.get("rubric_id") == "rubric-1.1":
        record_pass("Project detail includes rubric_id and pass status")
    else:
        record_fail("Project detail missing verdict info", str(verdict_info))

    v_json = verdict_info.get("json", {})
    criteria = v_json.get("judge", {}).get("criteria", [])
    if len(criteria) >= 2 and any("evidence" in c for c in criteria):
        record_pass("Project detail includes verified rubric criteria with evidence quotes")
    else:
        record_fail("Project detail missing quoted rubric evidence", str(criteria))

    # (b) Non-existent project GET /gallery/999 -> 404
    status, not_found_res = http_request("/gallery/999", method="GET", token=None)
    if status == 404:
        record_pass("GET /gallery/999 returns 404 Not Found")
    else:
        record_fail("Non-existent project should return 404", f"got {status}: {not_found_res}")

    # ------------------------------------------------------------------
    # 5. Spine Events & Student/Submission Queries
    # ------------------------------------------------------------------
    print("\n-- 5. Testing DB Spine Events & Student/Submission Queries --")

    # Check atomic events on DB spine
    events = db_sql("BEGIN;\nSELECT type, payload::text FROM events WHERE type IN ('gallery.published', 'gallery.unpublished') ORDER BY id ASC;\nROLLBACK;")
    event_types = [e[0] for e in events]

    if "gallery.published" in event_types:
        record_pass("Events table contains 'gallery.published' spine events")
    else:
        record_fail("Missing gallery.published events in DB", str(event_types))

    if "gallery.unpublished" in event_types:
        record_pass("Events table contains 'gallery.unpublished' spine event")
    else:
        record_fail("Missing gallery.unpublished events in DB", str(event_types))

    # Validate event payload structure
    pub_event = next((e for e in events if e[0] == "gallery.published"), None)
    if pub_event:
        payload = json.loads(pub_event[1])
        if "project_id" in payload and "student_id" in payload and "unit_id" in payload:
            record_pass("gallery.published event payload contains project_id, student_id, unit_id")
        else:
            record_fail("Malformed gallery.published payload", str(payload))

    # Query student's gallery entries: GET /students/1/gallery
    status, st_gallery = http_request("/students/1/gallery", method="GET")
    if status == 200 and len(st_gallery.get("projects", [])) == 1:
        record_pass("GET /students/1/gallery returns student's portfolio projects")
    else:
        record_fail("Student gallery query failed", str(st_gallery))

    # Query submission's gallery entry: GET /gallery/submission/1
    status, sub_gallery = http_request("/gallery/submission/1", method="GET")
    if status == 200 and sub_gallery.get("has_gallery_project") is True:
        record_pass("GET /gallery/submission/1 confirms linked gallery project exists")
    else:
        record_fail("Submission gallery query failed", str(sub_gallery))

    # Summary
    print(f"\nGallery Smoke Checks Complete: {passed_count} Passed, {failed_count} Failed")
    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
