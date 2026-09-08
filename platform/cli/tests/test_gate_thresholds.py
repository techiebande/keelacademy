"""Tests for the S1.6 gate thresholds: the margins that absorb judge variance
without absorbing a real rubric degradation."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # platform/cli
from grader.gate import (MIN_CRITERION_RATIO, MIN_OVERALL_RATIO,  # noqa: E402
                         evaluate)


def summary(*, total=15, overall_matches=15, criterion_total=75, criterion_matches=75, errors=0):
    return {
        "total": total,
        "overall_matches": overall_matches,
        "criterion_total": criterion_total,
        "criterion_matches": criterion_matches,
        "errors": errors,
    }


def test_perfect_summary_passes():
    passed, reasons = evaluate(summary())
    assert passed
    assert reasons == []


def test_any_judge_error_fails_even_at_full_agreement():
    passed, reasons = evaluate(summary(errors=1))
    assert not passed
    assert any("judge errors" in r for r in reasons)


def test_overall_margin_is_one_submission_at_15():
    # 14/15 is the ratified margin (judge variance), 13/15 is a degradation.
    assert evaluate(summary(overall_matches=14))[0] is True
    assert evaluate(summary(overall_matches=13))[0] is False


def test_criterion_margin_is_three_rows_at_75():
    assert evaluate(summary(criterion_matches=72))[0] is True
    assert evaluate(summary(criterion_matches=71))[0] is False


def test_thresholds_scale_by_ceiling_for_smaller_sets():
    # Golden 0.1 has 8 submissions after M5.2 adds the injection sample:
    # ceil(14/15 * 8) = 8, so a single overall miss fails.
    total = 8
    min_overall = math.ceil(MIN_OVERALL_RATIO * total)
    assert min_overall == 8
    assert evaluate(summary(total=total, overall_matches=8, criterion_total=40, criterion_matches=40))[0] is True
    assert evaluate(summary(total=total, overall_matches=7, criterion_total=40, criterion_matches=40))[0] is False
    # Criterion side: ceil(72/75 * 40) = 39.
    min_crit = math.ceil(MIN_CRITERION_RATIO * 40)
    assert min_crit == 39
    assert evaluate(summary(total=total, overall_matches=8, criterion_total=40, criterion_matches=39))[0] is True
    assert evaluate(summary(total=total, overall_matches=8, criterion_total=40, criterion_matches=38))[0] is False
