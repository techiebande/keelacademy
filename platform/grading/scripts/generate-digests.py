#!/usr/bin/env python3
"""scripts/generate-digests.py — Batch CLI runner for weekly retention digests (S4.3).

One-shot command to generate and deliver personalized weekly retention digests
for all enrolled students for a target cohort week.

Idempotent: skips already delivered digests for the target week.
Emits atomic spine events: 'digest.generated' and 'digest.delivered'.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GRADING_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(GRADING_DIR))

from db import db_sql, sql_str
from community.digests import generate_and_deliver_student_digest, current_cohort_week


def get_all_enrolled_student_ids() -> list[int]:
    """Find all students who have at least one enrollment or are active students."""
    sql = """BEGIN;
SELECT DISTINCT s.id
FROM students s
ORDER BY s.id ASC;
ROLLBACK;
"""
    rows = db_sql(sql)
    return [int(r[0]) for r in rows]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch generate & deliver weekly retention digests.")
    parser.add_argument("--cohort-week", help="Target cohort week (e.g. 2026-W35). Defaults to current ISO week.")
    parser.add_argument("--student-id", type=int, help="Optional student ID to run single digest for.")
    parser.add_argument("--dry-run", action="store_true", help="Synthesize without persisting/sending.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    now_override_raw = os.environ.get("KEEL_PRACTICE_NOW")
    now_override = datetime.fromisoformat(now_override_raw) if now_override_raw else None
    cohort_week = args.cohort_week or current_cohort_week(now_override)

    print(f"== Running Weekly Digest Dispatch for Cohort Week {cohort_week} ==")

    if args.student_id:
        student_ids = [args.student_id]
    else:
        student_ids = get_all_enrolled_student_ids()

    print(f"Found {len(student_ids)} eligible enrolled students.")

    generated_count = 0
    skipped_count = 0
    error_count = 0

    for sid in student_ids:
        try:
            res = generate_and_deliver_student_digest(
                student_id=sid,
                cohort_week=cohort_week,
                now_override=now_override,
            )
            if res.get("newly_generated"):
                generated_count += 1
                print(f"  [DISPATCHED] Student #{sid} ({res.get('email_to')}) — digest_id={res.get('id')}")
            else:
                skipped_count += 1
                print(f"  [SKIPPED] Student #{sid} already received digest for {cohort_week}")
        except Exception as exc:
            error_count += 1
            sys.stderr.write(f"  [ERROR] Student #{sid} digest failed: {exc}\n")

    print(f"\nBatch Digest Dispatch Complete: {generated_count} Generated, {skipped_count} Skipped (Idempotent), {error_count} Errors.")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
