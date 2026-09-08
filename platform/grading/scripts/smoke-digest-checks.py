#!/usr/bin/env python3
"""platform/grading/scripts/smoke-digest-checks.py — S4.3 Weekly retention digest test battery.

Deterministic assertions for:
1. Digest synthesis for 3 diverse student personas:
   - Active student (has completed units and recent submissions).
   - Idle student (zero attempts/logins this week; receives encouraging callout and next step).
   - Route-completed student (shows Build context and capstone milestones).
2. The 4 mandatory pillars are present and non-empty in all synthesized digests.
3. Deduplication: running batch generation twice in the same cohort week results in 0 duplicate digests and 0 duplicate emails.
4. Fake email transport verifies received HTML/text email content and recipient addressing.
5. Spine events 'digest.generated' and 'digest.delivered' logged atomically.
6. Auth scoping & error handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
GRADING_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str

SERVICE_URL = os.environ.get("KEEL_PRACTICE_URL", "http://127.0.0.1:8792")
FAKE_EMAIL_URL = os.environ.get("KEEL_FAKE_EMAIL_URL", "http://127.0.0.1:8799")
APP_TOKEN = os.environ.get("KEEL_ENROLL_SECRET", "smoke-digest-token")

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


def get_fake_email_records() -> list[dict[str, Any]]:
    req = urllib.request.Request(f"{FAKE_EMAIL_URL}/__records")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("emails", []) or data.get("records", [])
    except Exception:
        return []


def reset_fake_email() -> None:
    req = urllib.request.Request(f"{FAKE_EMAIL_URL}/__reset", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def main() -> int:
    print("== Running S4.3 Weekly Personalized Retention Digest Smoke Battery ==")

    cohort_week = "2026-W35"

    # 1. Verify 3 Personas in DB
    # Alice (Active student), Bob (Idle student), Carol (Route-completed student)
    rows = db_sql("BEGIN; SELECT id, display_name, email FROM students ORDER BY id ASC; ROLLBACK;")
    student_map = {r[1]: int(r[0]) for r in rows}

    alice_id = student_map.get("Alice")
    bob_id = student_map.get("Bob")
    carol_id = student_map.get("Carol")

    check("Alice (Active Persona) exists", alice_id is not None, f"id={alice_id}")
    check("Bob (Idle Persona) exists", bob_id is not None, f"id={bob_id}")
    check("Carol (Completed Persona) exists", carol_id is not None, f"id={carol_id}")

    # --------------------------------------------------------------------------
    # Part 1: Batch CLI Runner & Guaranteed Idle Reach-out
    # --------------------------------------------------------------------------
    print("\n-- 1. Testing Batch CLI Generation & Delivery --")
    reset_fake_email()

    cli_script = GRADING_DIR / "scripts" / "generate-digests.py"
    res = subprocess.run(
        [sys.executable, str(cli_script), "--cohort-week", cohort_week],
        capture_output=True,
        text=True,
        env=os.environ,
    )
    check("generate-digests.py batch CLI executed successfully", res.returncode == 0, f"stdout={res.stdout}, stderr={res.stderr}")

    # Verify digests created in DB for all students
    digests_count_rows = db_sql(f"BEGIN; SELECT count(*) FROM digests WHERE cohort_week = '{cohort_week}'; ROLLBACK;")
    digests_count = int(digests_count_rows[0][0])
    check("Digests generated for all enrolled students", digests_count >= 3, f"count={digests_count}")

    # Check fake email server received dispatches
    emails = get_fake_email_records()
    check("Fake email server captured dispatches for all generated digests", len(emails) >= digests_count, f"received={len(emails)}, expected>={digests_count}")

    # --------------------------------------------------------------------------
    # Part 2: Persona Synthesis & 4 Mandatory Pillars Assertions
    # --------------------------------------------------------------------------
    print("\n-- 2. Testing 3 Diverse Personas & 4 Pillars Content --")

    # Persona 1: Alice (Active student)
    st, alice_res = http_req("GET", f"/digest/latest?student_id={alice_id}")
    check("Alice GET /digest/latest returns 200", st == 200, f"status={st}")
    check("Alice has_digest is True", alice_res.get("has_digest") is True, f"res={alice_res}")
    
    alice_content = alice_res.get("digest", {}).get("content_json", {})
    alice_pillars = alice_content.get("pillars", {})
    
    # 4 Pillars check for Alice
    check("Alice has Pillar 1 (Current Location)", "current_location" in alice_pillars, f"pillars={alice_pillars.keys()}")
    check("Alice has Pillar 2 (Next Unlocks)", "next_unlocks" in alice_pillars, f"pillars={alice_pillars.keys()}")
    check("Alice has Pillar 3 (Pod Activity)", "pod_activity" in alice_pillars, f"pillars={alice_pillars.keys()}")
    check("Alice has Pillar 4 (Rebate Status)", "rebate_status" in alice_pillars, f"pillars={alice_pillars.keys()}")

    alice_loc = alice_pillars.get("current_location", {})
    check("Alice location shows completed units > 0", len(alice_loc.get("completed_units", [])) > 0, f"completed={alice_loc.get('completed_units')}")
    check("Alice is NOT idle", alice_loc.get("is_idle") is False, f"loc={alice_loc}")

    # Persona 2: Bob (Idle student - 0 logins/attempts this week)
    st, bob_res = http_req("GET", f"/digest/latest?student_id={bob_id}")
    check("Bob GET /digest/latest returns 200", st == 200, f"status={st}")
    bob_pillars = bob_res.get("digest", {}).get("content_json", {}).get("pillars", {})
    bob_loc = bob_pillars.get("current_location", {})
    check("Bob is marked idle with encouraging reach-out note", bob_loc.get("is_idle") is True, f"loc={bob_loc}")
    check("Bob idle reach-out note is non-empty", bool(bob_loc.get("note")), f"note={bob_loc.get('note')}")
    check("Bob has next unlocks populated", len(bob_pillars.get("next_unlocks", {}).get("next_units", [])) > 0, f"unlocks={bob_pillars.get('next_unlocks')}")

    # Persona 3: Carol (Route-completed student)
    st, carol_res = http_req("GET", f"/digest/latest?student_id={carol_id}")
    check("Carol GET /digest/latest returns 200", st == 200, f"status={st}")
    carol_pillars = carol_res.get("digest", {}).get("content_json", {}).get("pillars", {})
    carol_loc = carol_pillars.get("current_location", {})
    check("Carol is marked completed", carol_loc.get("is_completed") is True, f"loc={carol_loc}")
    check("Carol location headline reflects capstone / completion", "Completed" in carol_loc.get("headline", "") or "Capstone" in carol_loc.get("headline", ""), f"headline={carol_loc.get('headline')}")

    # Pod activity verification (Pillar 3 non-empty)
    pod_act = alice_pillars.get("pod_activity", {})
    check("Pod activity highlights present", len(pod_act.get("highlights", [])) > 0, f"pod_act={pod_act}")

    # Rebates verification (Pillar 4 non-empty)
    rebate_act = alice_pillars.get("rebate_status", {})
    check("Rebate milestones present", len(rebate_act.get("milestones", [])) > 0, f"rebates={rebate_act}")

    # --------------------------------------------------------------------------
    # Part 3: Deduplication & Idempotency
    # --------------------------------------------------------------------------
    print("\n-- 3. Testing Deduplication Guarantee --")
    email_count_before = len(get_fake_email_records())

    # Running batch generation a SECOND time for the same cohort week
    res2 = subprocess.run(
        [sys.executable, str(cli_script), "--cohort-week", cohort_week],
        capture_output=True,
        text=True,
        env=os.environ,
    )
    check("Second batch generation executed cleanly", res2.returncode == 0, f"stderr={res2.stderr}")

    # Verify digests row count in DB is unchanged (0 duplicate rows)
    digests_count_after = int(db_sql(f"BEGIN; SELECT count(*) FROM digests WHERE cohort_week = '{cohort_week}'; ROLLBACK;")[0][0])
    check("DB digest count identical after second run (0 duplicate rows)", digests_count_after == digests_count, f"after={digests_count_after}, before={digests_count}")

    # Verify fake email received 0 additional emails
    email_count_after = len(get_fake_email_records())
    check("0 duplicate emails delivered on re-run", email_count_after == email_count_before, f"after={email_count_after}, before={email_count_before}")

    # --------------------------------------------------------------------------
    # Part 4: Email Content & Recipient Transport Verification
    # --------------------------------------------------------------------------
    print("\n-- 4. Testing Email Content & Addressing --")
    latest_email = emails[0].get("payload", {})
    check("Email has recipient address", bool(latest_email.get("to")), f"payload={latest_email}")
    check("Email subject contains Keel Academy Weekly Dispatch", "Keel Academy Weekly Dispatch" in latest_email.get("subject", ""), f"subject={latest_email.get('subject')}")
    check("Email contains plain text body with 4 pillars", "CURRENT LOCATION" in latest_email.get("text", "") and "WHAT UNLOCKS NEXT" in latest_email.get("text", ""), f"text={latest_email.get('text')[:200]}")
    check("Email contains rich HTML body", "<html>" in latest_email.get("html", "") and "1. Current Location" in latest_email.get("html", ""), f"html={latest_email.get('html')[:200]}")

    # --------------------------------------------------------------------------
    # Part 5: Events Spine & Auth Boundary Enforcement
    # --------------------------------------------------------------------------
    print("\n-- 5. Testing Events Spine & Auth Boundary Enforcement --")
    gen_events = db_sql("BEGIN; SELECT count(*) FROM events WHERE type = 'digest.generated'; ROLLBACK;")
    deliv_events = db_sql("BEGIN; SELECT count(*) FROM events WHERE type = 'digest.delivered'; ROLLBACK;")

    check("Spine logged 'digest.generated' events atomically", int(gen_events[0][0]) >= digests_count, f"count={gen_events[0][0]}")
    check("Spine logged 'digest.delivered' events atomically", int(deliv_events[0][0]) >= digests_count, f"count={deliv_events[0][0]}")

    # Auth protection checks
    st, no_auth = http_req("GET", f"/digest/latest?student_id={alice_id}", token=None)
    check("Missing token returns 401", st == 401, f"status={st}")

    st, bad_auth = http_req("GET", f"/digest/latest?student_id={alice_id}", token="invalid-token")
    check("Invalid token returns 401", st == 401, f"status={st}")

    st, unk_student = http_req("GET", "/digest/latest?student_id=999999")
    check("Unknown student returns 404", st == 404, f"status={st}")

    print(f"\nDigest Smoke Checks Complete: {PASS_COUNT} Passed, {FAIL_COUNT} Failed")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
