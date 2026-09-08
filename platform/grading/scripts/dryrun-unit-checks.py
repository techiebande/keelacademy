#!/usr/bin/env python3
"""platform/grading/scripts/dryrun-unit-checks.py — S2.2 + S3.1 content-PR dry-run.

Runs a unit's deterministic Layer-1 checks against reference solutions so
a content change that breaks them fails loudly before merge (CI step of
content-gate.yml; also runnable directly).

Checks verified:
1. Build deliverable (S2.2): golden s01-textbook submission with the variant
   corpus placed at claims_messy.jsonl -> 8 pass / 0 fail, overall=pass.
2. Completion problem discrimination (S3.1):
   - Unfilled base problem -> 1 pass / 2 fail, overall=fail (expected red shape).
   - Worked-example solution -> 3 pass / 0 fail, overall=pass (expected green shape).
   - Set equality asserted on completion check IDs.

Offline by construction — Layer 1 only, no judge, no API key.
Prints shape lines; exit 0 on all shapes matching, exit 1 on shape drift,
exit 2 on setup/infrastructure failure.

Environment contract (layer1.py's, extended):
  KEEL_SANDBOX_IMAGE   defaults here to keel-runner:0.1 (the S0.3 image:
                       python:3.12-slim + pydantic 2.13.4 + pytest 9.1.1 —
                       layer1's own alpine default lacks both).
  KEEL_CONTENT_ROOT    content/ root used for golden, corpus, and checks lookup.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
GRADING_DIR = SCRIPT_DIR.parent
LAYER1 = GRADING_DIR / "layer1.py"
DEFAULT_IMAGE = "keel-runner:0.1"
DEFAULT_UNIT = "3.2.1"
DEFAULT_GOLDEN = "s01-textbook"
DEFAULT_CORPUS = "s14-artifact-evidence/claims_messy.jsonl"
DEFAULT_TIMEOUT_S = 60

# Add grading dir to sys.path to import layer1 directly for completion checks
sys.path.insert(0, str(GRADING_DIR))
import layer1

REFERENCE_CHECK_IDS = (
    "schema-object-importable",
    "twenty-in-twenty-out",
    "outputs-are-valid-schema-objects",
    "fallback-never-raises-never-drops",
    "failures-logged",
    "end-to-end-run-conserves-records",
    "end-to-end-run-logs-fallbacks",
    "logged-failures-name-the-claim",
)

COMPLETION_CHECK_IDS = (
    "completion-tests-green",
    "no-gap-markers-remain",
    "pipeline-runs-end-to-end",
)

EXPECTED_BASE_STATUSES = {
    "completion-tests-green": "fail",
    "no-gap-markers-remain": "fail",
    "pipeline-runs-end-to-end": "pass",
}


class DryRunError(Exception):
    pass


def content_root() -> Path:
    root = os.environ.get("KEEL_CONTENT_ROOT")
    if root:
        return Path(root).resolve()
    return SCRIPT_DIR.parents[2] / "content"


def stage_reference(root: Path, unit: str, golden: str, corpus: str,
                    submission: Path) -> None:
    golden_dir = root / "golden" / unit / golden
    corpus_file = root / "golden" / unit / corpus
    if not golden_dir.is_dir():
        raise DryRunError(f"reference solution not found: {golden_dir}")
    if not corpus_file.is_file():
        raise DryRunError(f"claims corpus not found: {corpus_file}")
    shutil.copytree(golden_dir, submission)
    shutil.copy(corpus_file, submission / "claims_messy.jsonl")


def run_layer1_build(submission: Path, unit: str, timeout_s: float) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("KEEL_SANDBOX_IMAGE", DEFAULT_IMAGE)
    env["KEEL_CONTENT_ROOT"] = str(content_root())
    proc = subprocess.run(
        [sys.executable, str(LAYER1), "--submission", str(submission),
         "--unit", unit, "--timeout", str(timeout_s)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        raise DryRunError(
            "layer1 infrastructure failure (is Docker running and %s present? "
            "build it with: docker build -t %s - <<< a Dockerfile of "
            "python:3.12-slim + pydantic==2.13.4 + pytest==9.1.1 — see the "
            "content-gate.yml dry-run step)"
            % (env["KEEL_SANDBOX_IMAGE"], env["KEEL_SANDBOX_IMAGE"]))
    return json.loads(proc.stdout.decode().strip().splitlines()[-1])


def assert_build_shape(result: dict[str, Any], unit: str) -> int:
    expected = set(REFERENCE_CHECK_IDS)
    by_id = {c.get("id"): c for c in result.get("checks", [])}
    n_pass = sum(1 for c in by_id.values() if c.get("status") == "pass")
    n_fail = len(by_id) - n_pass
    overall = result.get("overall")

    missing = sorted(expected - set(by_id))
    extra = sorted(set(by_id) - expected)
    drifted = sorted(cid for cid, c in by_id.items()
                     if cid in expected and c.get("status") != "pass")
    shape_ok = not (missing or extra or drifted) and overall == "pass"

    print("dry-run %s build: reference shape %s — %d pass / %d fail, overall=%s"
          % (unit, "OK" if shape_ok else "DRIFTED", n_pass, n_fail, overall))
    for cid in missing:
        print("  [missing] %s — expected but not run (checks file changed?)"
              % cid)
    for cid in extra:
        print("  [extra]   %s — not part of the reference shape" % cid)
    for cid in drifted:
        c = by_id[cid]
        print("  [%s] %s — %s" % (c.get("status"), cid, c.get("note")))
    return 0 if shape_ok else 1


def dryrun_completion(root: Path, unit: str, timeout_s: float) -> int:
    """Dry-run completion problem checks over unfilled base and worked example (S3.1)."""
    matches = sorted(root.glob(f"units/*/{unit}/unit.yaml"))
    if not matches:
        raise DryRunError(f"no unit.yaml for unit {unit!r} under {root}/units/")
    unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    practice = unit_data.get("practice") or {}
    completion = practice.get("completion_problem")
    if not completion:
        print(f"dry-run {unit} completion: no completion problem configured (skipped)")
        return 0

    base_rel = completion.get("base")
    checks_rel = completion.get("checks")
    we_rel = practice.get("worked_example")

    base_dir = root / base_rel
    checks_path = root / checks_rel
    we_dir = root / we_rel if we_rel else None

    if not base_dir.is_dir():
        raise DryRunError(f"completion base dir not found: {base_dir}")
    if not checks_path.is_file():
        raise DryRunError(f"completion checks file not found: {checks_path}")
    if not we_dir or not we_dir.is_dir():
        raise DryRunError(f"worked example dir not found: {we_dir}")

    checks_data = yaml.safe_load(checks_path.read_text(encoding="utf-8"))
    if not isinstance(checks_data, list):
        raise DryRunError(f"completion checks file is not a list: {checks_path}")

    expected_ids = set(COMPLETION_CHECK_IDS)
    actual_ids = {c.get("id") for c in checks_data if isinstance(c, dict)}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        print(f"dry-run {unit} completion: check IDs DRIFTED from specification")
        for cid in missing:
            print(f"  [missing] {cid}")
        for cid in extra:
            print(f"  [extra]   {cid}")
        return 1

    # Part A: Test unfilled base
    staging_base = Path(tempfile.mkdtemp(prefix="keel-dryrun-comp-base-"))
    try:
        sub_base = staging_base / "submission"
        target_base = sub_base / base_rel.rstrip("/")
        shutil.copytree(base_dir, target_base)
        results_base = [layer1.run_check_container(c, sub_base, timeout_s) for c in checks_data]
    finally:
        layer1.cleanup_staging(staging_base)

    base_by_id = {r.get("id"): r for r in results_base}
    base_pass = sum(1 for r in results_base if r.get("status") == "pass")
    base_fail = len(results_base) - base_pass
    base_overall = "pass" if all(r.get("status") == "pass" for r in results_base) else "fail"

    base_drifted = []
    for cid, exp_status in EXPECTED_BASE_STATUSES.items():
        if base_by_id.get(cid, {}).get("status") != exp_status:
            base_drifted.append(cid)

    base_ok = not base_drifted and base_overall == "fail"
    print("dry-run %s completion base: shape %s — %d pass / %d fail, overall=%s"
          % (unit, "OK" if base_ok else "DRIFTED", base_pass, base_fail, base_overall))
    for cid in base_drifted:
        r = base_by_id.get(cid, {})
        print("  [%s] %s — expected %s, got %s (%s)"
              % (r.get("status"), cid, EXPECTED_BASE_STATUSES[cid], r.get("status"), r.get("note")))

    # Part B: Test worked-example solution
    staging_we = Path(tempfile.mkdtemp(prefix="keel-dryrun-comp-we-"))
    try:
        sub_we = staging_we / "submission"
        target_we = sub_we / base_rel.rstrip("/")
        shutil.copytree(base_dir, target_we)
        # Override editable files from worked example
        for fname in ["schemas.py", "extractor.py"]:
            if (we_dir / fname).is_file():
                shutil.copy(we_dir / fname, target_we / fname)
        results_we = [layer1.run_check_container(c, sub_we, timeout_s) for c in checks_data]
    finally:
        layer1.cleanup_staging(staging_we)

    we_by_id = {r.get("id"): r for r in results_we}
    we_pass = sum(1 for r in results_we if r.get("status") == "pass")
    we_fail = len(results_we) - we_pass
    we_overall = "pass" if all(r.get("status") == "pass" for r in results_we) else "fail"

    we_drifted = [cid for cid, r in we_by_id.items() if r.get("status") != "pass"]
    we_ok = not we_drifted and we_overall == "pass"

    print("dry-run %s completion solution: shape %s — %d pass / %d fail, overall=%s"
          % (unit, "OK" if we_ok else "DRIFTED", we_pass, we_fail, we_overall))
    for cid in we_drifted:
        r = we_by_id[cid]
        print("  [%s] %s — %s" % (r.get("status"), cid, r.get("note")))

    return 0 if (base_ok and we_ok) else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="dryrun-unit-checks.py",
        description="Dry-run a unit's Layer-1 checks against reference "
                    "solutions (build deliverable and completion problem).")
    ap.add_argument("--unit", default=DEFAULT_UNIT)
    ap.add_argument("--golden", default=DEFAULT_GOLDEN,
                     help="golden submission used as the reference solution")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                     help="claims corpus substituted at claims_messy.jsonl")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                     help="per-check wall cap in seconds")
    ap.add_argument("--only-build", action="store_true",
                     help="run only the build reference dry-run")
    ap.add_argument("--only-completion", action="store_true",
                     help="run only the completion problem dry-run")
    args = ap.parse_args()

    os.environ.setdefault("KEEL_SANDBOX_IMAGE", DEFAULT_IMAGE)
    root = content_root()
    matches = sorted(root.glob(f"units/*/{args.unit}/unit.yaml"))
    if not matches:
        print(f"dry-run {args.unit}: unit not authored on disk (authoring reset, skipped)")
        return 0

    exit_build = 0
    if not args.only_completion:
        staging = Path(tempfile.mkdtemp(prefix="keel-dryrun-build-"))
        try:
            submission = staging / "submission"
            stage_reference(root, args.unit, args.golden, args.corpus, submission)
            result = run_layer1_build(submission, args.unit, args.timeout)
            exit_build = assert_build_shape(result, args.unit)
        except DryRunError as exc:
            print(f"error in build dry-run: {exc}", file=sys.stderr)
            return 2
        finally:
            layer1.cleanup_staging(staging)

    exit_comp = 0
    if not args.only_build:
        try:
            exit_comp = dryrun_completion(root, args.unit, args.timeout)
        except DryRunError as exc:
            print(f"error in completion dry-run: {exc}", file=sys.stderr)
            return 2

    return 0 if (exit_build == 0 and exit_comp == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
