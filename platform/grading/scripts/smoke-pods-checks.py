#!/usr/bin/env python3
"""platform/grading/scripts/smoke-pods-checks.py — S4.2 Pod tooling & weekly post flow test battery.

Deterministic assertions for:
1. Pod allocation boundaries: auto-filling pods to 6–10 students and spawning subsequent pods cleanly.
2. Weekly post submission: validating the 3 mandatory pillars (shipped, broke, next), rejecting incomplete/empty submissions, and enforcing one post per student per week.
3. Discord webhook/message delivery against fake_discord.py verifying payload structure and message ID tracking.
4. Atomic spine event emission ('pod.assigned', 'pod.post_submitted').
5. Auth boundary enforcement (unauthorized 401, unknown student 404, non-member post 403, duplicate post 409, invalid payload 422).
6. Pod retrieval endpoints (GET /pod/members and GET /pod/posts).
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
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str

SERVICE_URL = os.environ.get("KEEL_PRACTICE_URL", "http://127.0.0.1:8792")
FAKE_DISCORD_URL = os.environ.get("KEEL_DISCORD_API_URL", "http://127.0.0.1:8798")
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "smoke-pods-token")

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


def get_fake_discord_records() -> list[dict[str, Any]]:
    req = urllib.request.Request(f"{FAKE_DISCORD_URL}/__records")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("records", [])
    except Exception:
        return []


def main() -> int:
    print("== Running S4.2 Pod Tooling & Weekly Post Flow Smoke Battery ==")

    # 1. Fetch seeded students from DB
    rows = db_sql("BEGIN; SELECT id, email FROM students ORDER BY id ASC; ROLLBACK;")
    student_map = {r[1]: int(r[0]) for r in rows}
    
    # We should have at least 15 seeded students to test pod filling up to 10 and spawning Pod B
    check("Seeded students available (>= 15)", len(student_map) >= 15, f"total={len(student_map)}")
    
    students_list = sorted(student_map.values())
    first_10_students = students_list[:10]
    next_5_students = students_list[10:15]

    cohort_week = "2026-W35"

    # --------------------------------------------------------------------------
    # Part 1: Pod Allocation & Capacity Boundaries (6-10 students -> Spawn new pod)
    # --------------------------------------------------------------------------
    print("\n-- 1. Testing Pod Allocation Capacity & Spawn Boundaries --")
    pod_a_id = None

    for idx, sid in enumerate(first_10_students):
        st, res = http_req("POST", "/pod/assign", {
            "student_id": sid,
            "cohort_week": cohort_week,
        })
        check(f"Student {idx+1} assign returns 200", st == 200, f"status={st}, res={res}")
        check(f"Student {idx+1} newly_assigned is True", res.get("newly_assigned") is True, f"res={res}")
        
        if pod_a_id is None:
            pod_a_id = res.get("pod_id")
            check("First pod created with cohort week", res.get("cohort_week") == cohort_week, f"res={res}")
        else:
            check(f"Student {idx+1} assigned to Pod A ({pod_a_id})", res.get("pod_id") == pod_a_id, f"pod_id={res.get('pod_id')}")

    # Idempotency check: Re-assigning student 1 returns existing pod membership with newly_assigned=False
    st, idemp_res = http_req("POST", "/pod/assign", {
        "student_id": first_10_students[0],
        "cohort_week": cohort_week,
    })
    check("Re-assigning existing member returns 200", st == 200, f"status={st}")
    check("Re-assignment returns newly_assigned=False", idemp_res.get("newly_assigned") is False, f"res={idemp_res}")
    check("Re-assignment returns same Pod A id", idemp_res.get("pod_id") == pod_a_id, f"res={idemp_res}")

    # Now Pod A has exactly 10 members (MAX_POD_CAPACITY).
    # Assigning the 11th student should cleanly spawn Pod B for the same cohort week.
    st, pod_b_first = http_req("POST", "/pod/assign", {
        "student_id": next_5_students[0],
        "cohort_week": cohort_week,
    })
    check("11th student assign returns 200", st == 200, f"status={st}, res={pod_b_first}")
    pod_b_id = pod_b_first.get("pod_id")
    check("11th student allocated to new Pod B (different ID)", pod_b_id is not None and pod_b_id != pod_a_id, f"pod_b_id={pod_b_id}, pod_a_id={pod_a_id}")
    check("Pod B retains same cohort week", pod_b_first.get("cohort_week") == cohort_week, f"res={pod_b_first}")

    # Assign remaining students (12..15) into Pod B
    for idx, sid in enumerate(next_5_students[1:]):
        st, res = http_req("POST", "/pod/assign", {
            "student_id": sid,
            "cohort_week": cohort_week,
        })
        check(f"Student {idx+12} assigned to Pod B", res.get("pod_id") == pod_b_id, f"res={res}")

    # Verify pod.assigned spine events in DB
    assigned_events = db_sql("BEGIN; SELECT count(*) FROM events WHERE type = 'pod.assigned'; ROLLBACK;")
    check("DB has 15 pod.assigned events", int(assigned_events[0][0]) == 15, f"count={assigned_events[0][0]}")

    # --------------------------------------------------------------------------
    # Part 2: Pod Retrieval Endpoints (GET /pod/members, GET /pod/posts)
    # --------------------------------------------------------------------------
    print("\n-- 2. Testing Pod Retrieval Endpoints --")
    st, mem_res = http_req("GET", f"/pod/members?student_id={first_10_students[0]}")
    check("GET /pod/members returns 200", st == 200, f"status={st}")
    check("Student has_pod is True", mem_res.get("has_pod") is True, f"res={mem_res}")
    pod_details = mem_res.get("pod") or {}
    check("Pod details name matches", pod_details.get("pod_id") == pod_a_id, f"details={pod_details}")
    check("Pod details peer count is 10", len(pod_details.get("peers", [])) == 10, f"peers_count={len(pod_details.get('peers', []))}")
    check("Discord channel deep link present", bool(pod_details.get("discord_channel_id")), f"details={pod_details}")

    # --------------------------------------------------------------------------
    # Part 3: Weekly Post Flow (3 Pillars Validation, Uniqueness, Idempotency)
    # --------------------------------------------------------------------------
    print("\n-- 3. Testing Weekly Post Flow & 3-Pillar Validation --")
    alice_id = first_10_students[0]

    # Rejection: Missing shipped_text
    st, rej1 = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "",
        "broke_text": "Broke test suite",
        "next_text": "Next unit 1.2",
    })
    check("Missing shipped_text rejected with 422", st == 422, f"status={st}, res={rej1}")

    # Rejection: Missing broke_text
    st, rej2 = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Shipped unit 1.1",
        "broke_text": "   ",
        "next_text": "Next unit 1.2",
    })
    check("Missing broke_text rejected with 422", st == 422, f"status={st}, res={rej2}")

    # Rejection: Missing next_text
    st, rej3 = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Shipped unit 1.1",
        "broke_text": "Broke test suite",
        "next_text": "",
    })
    check("Missing next_text rejected with 422", st == 422, f"status={st}, res={rej3}")

    # Rejection: Non-member student attempting to post to Pod A
    carol_pod_b_id = next_5_students[0]
    st, rej_nonmember = http_req("POST", "/pod/posts", {
        "student_id": carol_pod_b_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Shipped unit 1.1",
        "broke_text": "Broke test suite",
        "next_text": "Next unit 1.2",
    })
    check("Non-member posting to pod returns 403", st == 403, f"status={st}, res={rej_nonmember}")

    # Successful valid submission for Alice (Week 1)
    st, valid_post = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Shipped Unit 1.1 Pydantic extraction parser & tests",
        "broke_text": "Enum deserialization broke on malformed uppercase status strings",
        "next_text": "Implement Layer-1 sandbox grading harness for Unit 1.2",
    })
    check("Valid weekly post submission returns 200", st == 200, f"status={st}, res={valid_post}")
    check("Submission returns post_id", bool(valid_post.get("post_id")), f"res={valid_post}")
    check("Submission recorded discord_message_id", bool(valid_post.get("discord_message_id")), f"res={valid_post}")

    # Uniqueness constraint: Alice attempting a duplicate post for Week 1 in Pod A returns 409
    st, dup_post = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Duplicate submission attempt",
        "broke_text": "Duplicate submission attempt",
        "next_text": "Duplicate submission attempt",
    })
    check("Duplicate weekly post for same week returns 409 Conflict", st == 409, f"status={st}, res={dup_post}")

    # Alice submitting for Week 2 succeeds
    st, week2_post = http_req("POST", "/pod/posts", {
        "student_id": alice_id,
        "pod_id": pod_a_id,
        "week_number": 2,
        "shipped_text": "Shipped Unit 1.2 sandbox runner",
        "broke_text": "Docker volume mount permissions on scratch dir",
        "next_text": "Unit 1.3 LLM proxy budget tracking",
    })
    check("Week 2 weekly post submission returns 200", st == 200, f"status={st}, res={week2_post}")

    # Another member (Student 2) submitting Week 1 post
    bob_id = first_10_students[1]
    st, bob_post = http_req("POST", "/pod/posts", {
        "student_id": bob_id,
        "pod_id": pod_a_id,
        "week_number": 1,
        "shipped_text": "Passed retrieval drill for structured generation",
        "broke_text": "Initial prompt injection probe allowed system prompt override",
        "next_text": "Complete completion problem 1.1",
    })
    check("Bob Week 1 weekly post returns 200", st == 200, f"status={st}, res={bob_post}")

    # Verify GET /pod/posts returns submitted posts
    st, posts_feed = http_req("GET", f"/pod/posts?pod_id={pod_a_id}")
    check("GET /pod/posts returns 200", st == 200, f"status={st}")
    check("GET /pod/posts returns all 3 submitted posts", len(posts_feed.get("posts", [])) == 3, f"feed={posts_feed}")

    # Verify week filter: GET /pod/posts?pod_id=<id>&week=1 returns 2 posts (Alice + Bob)
    st, week1_feed = http_req("GET", f"/pod/posts?pod_id={pod_a_id}&week=1")
    check("GET /pod/posts?week=1 returns 200", st == 200, f"status={st}")
    check("Week 1 filter returns 2 posts", len(week1_feed.get("posts", [])) == 2, f"feed={week1_feed}")

    # --------------------------------------------------------------------------
    # Part 4: Discord Webhook Relay Verification
    # --------------------------------------------------------------------------
    print("\n-- 4. Testing Discord Webhook Relay & Embed Verification --")
    discord_records = get_fake_discord_records()
    check("Discord fake received relayed messages (>= 3)", len(discord_records) >= 3, f"count={len(discord_records)}")

    # Check structure of the relayed Discord payload
    latest_discord_payload = discord_records[-1].get("payload", {})
    embeds = latest_discord_payload.get("embeds", [])
    check("Discord payload contains embeds list", len(embeds) > 0, f"payload={latest_discord_payload}")
    if embeds:
        fields = embeds[0].get("fields", [])
        field_names = [f.get("name") for f in fields]
        check("Discord embed contains '1. What Shipped'", "1. What Shipped" in field_names, f"fields={field_names}")
        check("Discord embed contains '2. What Broke'", "2. What Broke" in field_names, f"fields={field_names}")
        check("Discord embed contains '3. What's Next'", "3. What's Next" in field_names, f"fields={field_names}")

    # --------------------------------------------------------------------------
    # Part 5: Events Spine & Auth Boundary Enforcement
    # --------------------------------------------------------------------------
    print("\n-- 5. Testing Events Spine & Auth Boundary Enforcement --")
    # Verify pod.post_submitted events on spine
    post_events = db_sql("BEGIN; SELECT payload->>'week_number', payload->>'student_id' FROM events WHERE type = 'pod.post_submitted' ORDER BY id ASC; ROLLBACK;")
    check("DB has 3 pod.post_submitted events", len(post_events) == 3, f"events={post_events}")

    # Auth protection checks
    st, no_auth = http_req("POST", "/pod/assign", {"student_id": alice_id}, token=None)
    check("Missing token returns 401", st == 401, f"status={st}")

    st, bad_auth = http_req("POST", "/pod/assign", {"student_id": alice_id}, token="invalid-token")
    check("Invalid token returns 401", st == 401, f"status={st}")

    st, unk_student = http_req("POST", "/pod/assign", {"student_id": 999999})
    check("Unknown student returns 404", st == 404, f"status={st}")

    st, unk_student_get = http_req("GET", "/pod/members?student_id=999999")
    check("Unknown student GET /pod/members returns 404", st == 404, f"status={st}")

    st, unk_pod_posts = http_req("GET", "/pod/posts?pod_id=999999")
    check("Unknown pod GET /pod/posts returns 404", st == 404, f"status={st}")

    print(f"\nPod Smoke Checks Complete: {PASS_COUNT} Passed, {FAIL_COUNT} Failed")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
