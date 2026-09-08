"""Judge-calibration harness against the golden set.

Usage:
    python -m grader.calibrate --golden content/golden/3.2.1 \
        --rubric content/rubrics/3.2.1/v1.yaml [--json report.json]

Iterates every submission directory under --golden in sorted order, judges it
via the SAME code path as the CLI (grader.judge.judge — no duplicated LLM
logic), compares the verdict against the reference grade.yaml (overall +
criterion-for-criterion), prints an agreement table, and writes a JSON report
if --json is given. This is the seed of the S1.6 golden-set regression gate.

Exit code: 0 iff overall agreement >= 90% AND zero errors; otherwise 1.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from .judge import JudgeError, judge
from .llm import LLMError, begin_trace_call, set_trace_caller, trace
from .submission import SubmissionError

OVERALL_THRESHOLD = 0.90

TRANSIENT_MARKERS = ("timed out", "connection reset", "name resolution",
                     "temporarily unavailable", "api unreachable", "rate limit")


def is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in TRANSIENT_MARKERS)


def judge_with_retry(submission_dir: Path, rubric_path: Path, attempts: int = 3) -> dict:
    """Network flakiness (DNS blips, resets, read timeouts) is common on long
    runs; retry transient failures so calibration measures grading, not the
    network. Non-transient judge errors propagate immediately."""
    begin_trace_call()  # attempt ordinal resets per submission; transient
    # retries and JSON-nudge retries both advance it within this call.
    for attempt in range(1, attempts + 1):
        try:
            return judge(submission_dir, rubric_path)
        except (JudgeError, LLMError) as exc:
            if attempt < attempts and is_transient(exc):
                print(f"transient error judging {submission_dir.name} "
                      f"(attempt {attempt}/{attempts}): {exc} — retrying", file=sys.stderr)
                time.sleep(5 * attempt)
                continue
            raise


def load_reference(grade_path: Path) -> dict:
    grade = yaml.safe_load(grade_path.read_text())
    for key in ("expected", "criteria", "overall"):
        if key not in grade:
            raise ValueError(f"{grade_path} missing key {key!r}")
    return grade


def overall_match(judged: str, reference: dict) -> bool:
    """A reference `expected` of pass/fail must match exactly. `expected:
    borderline` can never match a binary judge literally, so it counts as a
    match when the judge lands on the same side as the human's resolved binary
    `overall` in the same grade.yaml."""
    if reference["expected"] == "borderline":
        return judged == reference["overall"]
    return judged == reference["expected"]


def compare(verdict: dict, reference: dict) -> list[dict]:
    """Per-criterion comparison rows (only used for reports/tables)."""
    ref = reference["criteria"]
    judged = {c["id"]: c for c in verdict["criteria"]}
    rows = []
    for rid, ref_verdict in ref.items():
        jc = judged.get(rid)
        rows.append({
            "criterion": rid,
            "expected": ref_verdict,
            "judged": jc["verdict"] if jc else None,
            "match": bool(jc and jc["verdict"] == ref_verdict),
            "evidence": jc["evidence"] if jc else None,
        })
    return rows


def run_calibration(golden_dir: Path, rubric_path: Path) -> dict:
    """Judge every submission under golden_dir with rubric_path (same judge
    code path as the CLI), compare against each grade.yaml, print the
    agreement table, and return the full report dict. Shared by calibrate and
    the S1.6 gate (grader.gate) — one code path, no fork."""
    dirs = sorted(d for d in golden_dir.iterdir() if d.is_dir())
    if not dirs:
        raise ValueError(f"no submission dirs in {golden_dir}")

    results = []
    errors = 0
    for d in dirs:
        name = d.name
        try:
            reference = load_reference(d / "grade.yaml")
            verdict = judge_with_retry(d, rubric_path)
        except (JudgeError, SubmissionError, LLMError, ValueError, OSError) as exc:
            errors += 1
            print(f"ERROR judging {name}: {exc}", file=sys.stderr)
            results.append({"name": name, "status": "error", "error": str(exc)})
            continue
        trace(verdict["meta"])
        crit_rows = compare(verdict, reference)
        is_match = overall_match(verdict["overall"], reference)
        results.append({
            "name": name,
            "status": "match" if is_match else "miss",
            "expected": reference["expected"],
            "judged": verdict["overall"],
            "criteria": crit_rows,
            "meta": verdict["meta"],
        })
        print(f"{name:28} expected={reference['expected']:9} judged={verdict['overall']:4} "
              f"{'OVERALL MATCH' if is_match else 'OVERALL MISS'}")
        if not is_match:
            for r in crit_rows:
                if not r["match"]:
                    ev = (r["evidence"] or "").replace("\n", " ")[:160]
                    print(f"    {r['criterion']}: judge={r['judged']} ref={r['expected']}"
                          f"{'' if r['judged'] is None else '  | evidence: ' + ev}")

    graded = [r for r in results if r["status"] != "error"]
    overall_matches = sum(1 for r in graded if r["status"] == "match")
    crit_total = sum(len(r["criteria"]) for r in graded)
    crit_matches = sum(1 for r in graded for c in r["criteria"] if c["match"])
    overall_pct = (overall_matches / len(graded) * 100) if graded else 0.0
    crit_pct = (crit_matches / crit_total * 100) if crit_total else 0.0

    prompt_tokens = sum(r["meta"]["prompt_tokens"] for r in graded)
    completion_tokens = sum(r["meta"]["completion_tokens"] for r in graded)

    print(f"\nOverall agreement:    {overall_matches}/{len(graded)} ({overall_pct:.1f}%)")
    print(f"Criterion agreement:  {crit_matches}/{crit_total} ({crit_pct:.1f}%)")
    print(f"Errors:               {errors}")
    print(f"Tokens (graded runs): in={prompt_tokens} out={completion_tokens}")

    return {
        "golden": str(golden_dir),
        "rubric": str(rubric_path),
        "results": results,
        "summary": {
            "total": len(results),
            "overall_matches": overall_matches,
            "overall_agreement_pct": round(overall_pct, 2),
            "criterion_matches": crit_matches,
            "criterion_total": crit_total,
            "criterion_agreement_pct": round(crit_pct, 2),
            "errors": errors,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def write_report(report: dict, json_path: Path) -> None:
    json_path.write_text(json.dumps(report, indent=2))
    print(f"report written to {json_path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="grader.calibrate",
        description="judge-vs-golden-set agreement harness (seed of the S1.6 regression gate)")
    ap.add_argument("--golden", required=True, type=Path, help="golden set dir (e.g. content/golden/3.2.1)")
    ap.add_argument("--rubric", required=True, type=Path, help="rubric YAML")
    ap.add_argument("--json", type=Path, help="write the JSON report here")
    args = ap.parse_args(argv)

    set_trace_caller("calibrate", force=True)
    try:
        report = run_calibration(args.golden, args.rubric)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        write_report(report, args.json)

    s = report["summary"]
    ok = s["errors"] == 0 and s["overall_agreement_pct"] >= OVERALL_THRESHOLD * 100
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
