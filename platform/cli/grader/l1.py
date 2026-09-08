"""Layer-1 grading CLI.

Usage:
    python -m grader.l1 <submission_dir> --checks <checks.yaml> [--json out.json] [--timeout 120]

Runs each check in an isolated Docker container (no network, 512m mem, 1 cpu,
read-only submission mount) and reports per-check / per-test results.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .checks import Check, evaluate_expect, load_checks, remap_run_paths
from .runner import RunResult, run_check

OUTPUT_TAIL_CHARS = 2000


def grade(submission_dir: Path, checks: list[Check], timeout_s: int) -> list[dict]:
    results = []
    for check in checks:
        run = remap_run_paths(check.run, submission_dir)
        rr: RunResult = run_check(check.type, run, submission_dir, timeout_s)
        if rr.timed_out:
            status = "error"
            note = f"timed out after {timeout_s}s"
        elif check.type == "pytest":
            failing = [t for t in rr.tests if t.outcome not in ("pass", "skipped")]
            status = "pass" if (rr.exit_code == 0 and not failing and rr.tests) else "fail"
            if rr.exit_code != 0 and not rr.tests:
                status = "error"  # pytest itself blew up (collection error etc.)
            note = f"exit code {rr.exit_code}, {len(rr.tests)} tests"
        else:
            passed, note = evaluate_expect(check.expect, rr.exit_code, rr.output)
            status = "pass" if passed else "fail"
        results.append({
            "check_id": check.id,
            "type": check.type,
            "run": run,
            "status": status,
            "duration_s": round(rr.duration_s, 2),
            "note": note,
            "failing_tests": [
                {"nodeid": t.nodeid, "outcome": t.outcome, "message": t.message[:500]}
                for t in rr.tests if t.outcome not in ("pass", "skipped")
            ],
            "output_tail": rr.output[-OUTPUT_TAIL_CHARS:],
        })
    return results


def human_summary(results: list[dict], overall: bool) -> None:
    for r in results:
        print(f"[{r['status'].upper():5}] {r['check_id']} ({r['type']}, {r['duration_s']}s) — {r['note']}")
        for t in r["failing_tests"]:
            print(f"        FAIL {t['nodeid']}")
            if t["message"]:
                msg = t["message"].splitlines()[0] if t["message"] else ""
                print(f"             {msg[:160]}")
    print(f"\nOVERALL: {'PASS' if overall else 'FAIL'} ({sum(r['status'] == 'pass' for r in results)}/{len(results)} checks passed)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="grader.l1", description="keelacademy Layer-1 grading CLI")
    ap.add_argument("submission_dir", type=Path)
    ap.add_argument("--checks", required=True, type=Path, help="checks YAML in {id, type, run, expect} format")
    ap.add_argument("--json", type=Path, help="write machine verdict JSON here")
    ap.add_argument("--timeout", type=int, default=120, help="per-check wall-clock timeout in seconds")
    args = ap.parse_args(argv)

    if not args.submission_dir.is_dir():
        print(f"error: submission dir not found: {args.submission_dir}", file=sys.stderr)
        return 2
    checks = load_checks(args.checks)
    results = grade(args.submission_dir, checks, args.timeout)
    overall = all(r["status"] == "pass" for r in results)
    verdict = {
        "overall": "pass" if overall else "fail",
        "submission_dir": str(args.submission_dir.resolve()),
        "checks_file": str(args.checks.resolve()),
        "checks": results,
    }
    human_summary(results, overall)
    if args.json:
        args.json.write_text(json.dumps(verdict, indent=2))
        print(f"\nverdict JSON written to {args.json}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
