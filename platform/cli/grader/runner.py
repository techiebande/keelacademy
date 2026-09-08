"""Docker sandbox runner: one container per check, no network, hard caps.

The submission is mounted READ-ONLY at /work (the working dir); a per-check
scratch dir is mounted rw at /scratch for artifacts (junit XML, logs). Checks
can never write into the submission.
"""
from __future__ import annotations

import shlex
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

RUNNER_IMAGE = "keel-runner:0.1"
DEFAULT_TIMEOUT_S = 120


@dataclass
class TestResult:
    nodeid: str
    outcome: str  # pass | fail | error | skipped ...
    message: str = ""


@dataclass
class RunResult:
    exit_code: int | None  # None = timed out / could not run
    output: str
    tests: list[TestResult] = field(default_factory=list)
    timed_out: bool = False
    duration_s: float = 0.0


def run_check(
    check_type: str,
    run: str,
    submission_dir: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> RunResult:
    """Execute one check in a fresh container and return its result."""
    scratch = Path(subprocess.run(["mktemp", "-d"], capture_output=True, text=True, check=True).stdout.strip())
    # Make scratch writable by the container's default (root) user; we only read
    # artifacts back on the host afterwards.
    name = f"keel-grader-{uuid.uuid4().hex[:12]}"
    try:
        if check_type == "pytest":
            script = f"pytest {run} --junitxml=/scratch/results.xml"
        else:
            script = run
        cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none", "--memory", "512m", "--cpus", "1",
            "-v", f"{submission_dir.resolve()}:/work:ro",
            "-v", f"{scratch}:/scratch",
            "-w", "/work",
            RUNNER_IMAGE, "bash", "-c", script,
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
            duration = time.monotonic() - start
            tests = _parse_junit(scratch / "results.xml") if check_type == "pytest" else []
            return RunResult(
                exit_code=proc.returncode,
                output=proc.stdout + proc.stderr,
                tests=tests,
                duration_s=duration,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            return RunResult(
                exit_code=None,
                output=f"check exceeded wall-clock timeout of {timeout_s}s and was killed",
                timed_out=True,
                duration_s=time.monotonic() - start,
            )
    finally:
        subprocess.run(["rm", "-rf", scratch], capture_output=True)


def _parse_junit(xml_path: Path) -> list[TestResult]:
    if not xml_path.exists():
        return []
    results = []
    root = ET.parse(xml_path).getroot()
    # junitxml nests <testcase> under <testsuite> (pytest) and possibly
    # <testsuites>; walk all of them.
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        outcome = "pass"
        message = ""
        for child in case:
            if child.tag in ("failure", "error"):
                outcome = child.tag
                message = child.get("message", "") or (child.text or "")[:500]
            elif child.tag == "skipped":
                outcome = "skipped"
                message = child.get("message", "")
        results.append(TestResult(nodeid=_nodeid(case, classname, name), outcome=outcome, message=message))
    return results


def _nodeid(case: ET.Element, classname: str, name: str) -> str:
    # pytest 9's junit omits the `file` attribute; classname is the dotted
    # module path, so "tests.test_build" -> "tests/test_build.py::test_x".
    file_attr = case.get("file")
    if file_attr:
        return f"{file_attr}::{name}"
    if classname:
        return f"{classname.replace('.', '/')}.py::{name}"
    return name
