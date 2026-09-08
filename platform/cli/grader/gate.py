"""S1.6 golden-set regression gate for rubric changes.

Usage:
    python -m grader.gate --golden content/golden/3.2.1 \
        --rubric content/rubrics/3.2.1/v1.yaml [--json gate-report.json]

Runs the SAME calibration code path as grader.calibrate (run_calibration —
shared, not forked) over the golden set with a candidate rubric, then applies
gate thresholds.

Threshold rationale (baseline: S0.7 run, 15/15 overall, 75/75 criterion,
recorded in platform/cli/calibrate-after-s07.json): a dated ruling in
build-state.md established that the judge's per-criterion failure set can vary
between runs at temperature 0 while overall agreement stays stable. So the
gate is primarily on OVERALL agreement, with criterion agreement as a
secondary signal. The margins — one overall submission (14/15) and three
criterion verdicts (72/75) — absorb observed judge variance, while any real
rubric degradation flips multiple submissions and fails hard.

Exit code: 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from .calibrate import run_calibration, write_report
from .llm import set_trace_caller

# PASS requires: zero judge errors AND overall >= MIN_OVERALL_RATIO of graded
# submissions AND criterion >= MIN_CRITERION_RATIO of graded criterion rows.
# 14/15 and 72/75 respectively at the current golden-set size (15 submissions
# x 5 criteria); expressed as ratios so the gate scales if the set grows.
MIN_OVERALL_RATIO = 14 / 15
MIN_CRITERION_RATIO = 72 / 75


def evaluate(summary: dict) -> tuple[bool, list[str]]:
    """Apply gate thresholds to a calibration summary; returns (passed, reasons)."""
    reasons = []
    if summary["errors"] != 0:
        reasons.append(f"judge errors: {summary['errors']} (required: 0)")
    min_overall = math.ceil(MIN_OVERALL_RATIO * summary["total"])
    if summary["overall_matches"] < min_overall:
        reasons.append(
            f"overall agreement {summary['overall_matches']}/{summary['total']} "
            f"below required {min_overall}/{summary['total']}")
    min_crit = math.ceil(MIN_CRITERION_RATIO * summary["criterion_total"])
    if summary["criterion_matches"] < min_crit:
        reasons.append(
            f"criterion agreement {summary['criterion_matches']}/{summary['criterion_total']} "
            f"below required {min_crit}/{summary['criterion_total']}")
    return (not reasons, reasons)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="grader.gate",
        description="S1.6 golden-set regression gate: PASS iff zero errors AND "
                    f"overall agreement >= {MIN_OVERALL_RATIO:.0%} AND "
                    f"criterion agreement >= {MIN_CRITERION_RATIO:.0%}")
    ap.add_argument("--golden", required=True, type=Path, help="golden set dir (e.g. content/golden/3.2.1)")
    ap.add_argument("--rubric", required=True, type=Path, help="candidate rubric YAML")
    ap.add_argument("--json", type=Path, help="write the JSON report here")
    args = ap.parse_args(argv)

    set_trace_caller("gate", force=True)
    report = run_calibration(args.golden, args.rubric)

    passed, reasons = evaluate(report["summary"])
    report["gate"] = {"passed": passed, "thresholds": {
        "min_overall_ratio": MIN_OVERALL_RATIO,
        "min_criterion_ratio": MIN_CRITERION_RATIO,
    }, "reasons": reasons}
    if args.json:
        write_report(report, args.json)

    if passed:
        print("GATE: PASS")
        return 0
    print("GATE: FAIL", file=sys.stderr)
    for r in reasons:
        print(f"  - {r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
