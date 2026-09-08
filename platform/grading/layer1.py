#!/usr/bin/env python3
"""platform/grading/layer1.py — Layer-1 grading through the S1.4 sandbox (S1.8).

Runs a submission's deterministic checks (content/checks/<unit>.build.yaml,
located via the unit's unit.yaml `verify.deterministic_checks`) through the
hardened sandbox runner — one ephemeral, networkless container per check with
a per-check wall cap. Invoked by worker.py's GRADE step; prints one JSON
object to stdout:

    {"overall": "pass"|"fail",
     "checks": [{"id", "type", "status", "note", "wall_s",
                 "exit_code", "container_status", "output_tail"}],
     "injected": [...]}

Environment contract:
  KEEL_SANDBOX_IMAGE   passed through to the runner — set it to an image that
                       carries the dependencies the checks import (e.g.
                       keel-runner:0.1 with pytest + pydantic); defaults to
                       python:3.12-alpine.
  KEEL_CONTENT_ROOT    content/ root (defaults to the repo this file lives in).

Check execution model: the submission is copied to the container's writable
noexec tmpfs (/work) because several checks write artifacts (out.jsonl,
run.log) next to the code; the read-only /submission mount stays the source of
truth. A `proxy` mock module (deterministic: even-numbered notes get valid
schema JSON, odd-numbered notes get garbage, exercising the fallback path)
and, per the golden-set contract, the run is offline — Layer 1 never touches
the LLM proxy; that budget belongs to Layer 2.

Needs PyYAML (same interpreter environment as the grader CLIs); everything
else is stdlib.
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

import yaml

GRADING_DIR = Path(__file__).resolve().parent
RUNNER = GRADING_DIR / "sandbox" / "runner.py"
DEFAULT_TIMEOUT_S = 60
OUTPUT_TAIL_CHARS = 800

PROXY_MOCK = '''"""Injected platform proxy mock (offline Layer-1 grading; S1.8).

Deterministic stand-in for the student-visible LLM proxy: even-numbered
notes return schema-valid JSON, odd-numbered notes return garbage so the
fallback+logging path is exercised on every run. Never touches the network.
Submissions reference the proxy as a bare `proxy` name (per the golden-set
contract), so the mock installs itself into builtins via sitecustomize —
picked up automatically because the staged working dir is on sys.path for
every interpreter start inside the container.
"""
import builtins
import json
import re


class _Completions:
    def create(self, *, model=None, response_format=None, messages=None, **kw):
        user = [m for m in (messages or []) if m.get("role") == "user"]
        note = user[-1]["content"] if user else ""
        m = re.search(r"(\\d+)\\s*$", note.strip())
        n = int(m.group(1)) if m else 0
        if n % 2 == 0:
            content = json.dumps({"claim_type": "damage", "severity": "low"})
        else:
            content = "TOTALLY NOT JSON %d" % n
        msg = type("Msg", (), {"content": content})
        choice = type("Choice", (), {"message": msg})()
        return type("Resp", (), {"choices": [choice]})()


builtins.proxy = type("proxy", (), {
    "chat": type("Chat", (), {"completions": _Completions()})})
# Golden-set submissions also reference CONFIG (model switch) and
# SYSTEM_PROMPT as platform-injected names (see content/golden README).
builtins.CONFIG = type("Config", (), {"model": "fake-keel-model"})
builtins.SYSTEM_PROMPT = "Extract the claim fields as JSON."
'''


class Layer1Error(Exception):
    pass


def content_root() -> Path:
    root = os.environ.get("KEEL_CONTENT_ROOT")
    if root:
        return Path(root).resolve()
    return GRADING_DIR.parents[1] / "content"


def find_checks_path(unit_id: str) -> Path:
    """Locate the unit's checks file via its unit.yaml
    (verify.deterministic_checks, relative to the content root)."""
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if not matches:
        raise Layer1Error(f"no unit.yaml for unit {unit_id!r} under {root}/units/")
    unit = yaml.safe_load(matches[0].read_text())
    rel = (unit.get("verify") or {}).get("deterministic_checks")
    if not rel:
        raise Layer1Error(f"unit {unit_id!r} defines no verify.deterministic_checks")
    path = root / rel
    if not path.is_file():
        raise Layer1Error(f"checks file not found: {path}")
    return path


def evaluate_expect(expect, exit_code, output) -> tuple[bool, str]:
    """Same expect forms as the checks format: exit_zero, exit_nonzero,
    {output_contains: str} (evaluated against the runner's output tail)."""
    if exit_code is None:
        return False, "no exit code (contained/runner error)"
    if expect == "exit_zero":
        return exit_code == 0, f"exit code {exit_code}"
    if expect == "exit_nonzero":
        return exit_code != 0, f"exit code {exit_code}"
    if isinstance(expect, dict) and "output_contains" in expect:
        needle = str(expect["output_contains"])
        return needle in output, f"output_contains {needle!r}"
    return False, f"unknown expect {expect!r}"


def stage_submission(submission_dir: Path, staging: Path) -> list[str]:
    """Copy the submission into the staging dir and inject the offline proxy
    mock. Returns the list of injected artifacts (relative names)."""
    shutil.copytree(submission_dir, staging, dirs_exist_ok=True)
    (staging / "sitecustomize.py").write_text(PROXY_MOCK)
    return ["sitecustomize.py"]


def build_cmd(check: dict) -> str:
    run = check["run"]
    if check["type"] == "pytest":
        # python -m pytest puts the cwd on sys.path so tests can import the
        # submission's top-level modules from the copied working dir.
        run = f"python -m pytest {run}"
    # PYTHONPATH is what makes sitecustomize load: the interpreter sets
    # sys.path[0] only AFTER site init, so a cwd-local sitecustomize is never
    # auto-imported — PYTHONPATH dirs are on sys.path in time.
    return f"cp -r /submission/. /work/ && cd /work && export PYTHONPATH=/work && {run}"


def run_check_container(check: dict, staging: Path, default_timeout_s: float) -> dict:
    env = os.environ.copy()
    env["KEEL_SANDBOX_TIMEOUT_S"] = str(check.get("timeout_s", default_timeout_s))
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(staging), "--cmd", build_cmd(check)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    lines = [l for l in proc.stdout.decode().splitlines() if l.strip()]
    if proc.returncode != 0 or not lines:
        raise Layer1Error(
            "sandbox runner infrastructure failure for check %r (exit %d): %s"
            % (check.get("id"), proc.returncode,
               proc.stderr.decode(errors="replace")[-500:]))
    result = json.loads(lines[-1])

    exit_code = result.get("exit_code")
    if result.get("status") != "ok":
        status, note = "error", f"container status {result.get('status')}"
    else:
        passed, note = evaluate_expect(check.get("expect"), exit_code,
                                       result.get("output_tail", ""))
        status = "pass" if passed else "fail"
    return {
        "id": check.get("id"),
        "type": check.get("type"),
        "status": status,
        "note": note,
        "wall_s": result.get("wall_s"),
        "exit_code": exit_code,
        "container_status": result.get("status"),
        "output_tail": (result.get("output_tail") or "")[-OUTPUT_TAIL_CHARS:],
    }


def _docker_cli() -> str | None:
    """Resolve a usable docker CLI exactly like sandbox/runner.py (Linux CLI
    first, Docker Desktop's Windows binary as fallback), but return None
    instead of exiting when neither is usable."""
    docker = shutil.which("docker")
    if docker:
        probe = subprocess.run(
            [docker, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return docker
    fallback = "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
    if os.path.exists(fallback):
        return fallback
    return None


def cleanup_staging(parent: Path) -> None:
    """Leak-proof removal of a staging dir.

    Docker Desktop's Windows docker.exe leaves bind-mounted staging contents
    root-owned on the host, so shutil.rmtree(..., ignore_errors=True) silently
    fails and every grade would leak one undeletable /tmp/keel-layer1-* dir.
    Escalate: plain rmtree first; if the dir survives, rm it from inside a
    disposable container (root there can unlink root-owned files); if even
    that fails, say so loudly — debris is never silent."""
    image = os.environ.get("KEEL_SANDBOX_IMAGE", "python:3.12-alpine")
    shutil.rmtree(parent, ignore_errors=True)
    if not parent.exists():
        return
    docker = _docker_cli()
    if docker:
        subprocess.run(
            [docker, "run", "--rm",
             "-v", f"{parent.parent}:/cleanup", image,
             "rm", "-rf", f"/cleanup/{parent.name}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if parent.exists():
        sys.stderr.write(
            "[layer1] warning: staging debris at %s (needs manual removal)\n" % parent)


def grade(submission_dir: Path, unit_id: str, default_timeout_s: float) -> dict:
    checks = yaml.safe_load(find_checks_path(unit_id).read_text())
    if not isinstance(checks, list) or not checks:
        raise Layer1Error(f"checks file for {unit_id!r} is empty or not a list")

    staging_parent = Path(tempfile.mkdtemp(prefix="keel-layer1-"))
    staging = staging_parent / "submission"
    try:
        injected = stage_submission(submission_dir, staging)
        results = [run_check_container(c, staging, default_timeout_s) for c in checks]
        return {
            "overall": "pass" if all(r["status"] == "pass" for r in results) else "fail",
            "checks": results,
            "injected": injected,
        }
    finally:
        cleanup_staging(staging_parent)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="layer1.py",
        description="Run a submission's deterministic checks through the S1.4 sandbox.")
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                    help="per-check wall cap in seconds (checks may override via timeout_s)")
    args = ap.parse_args()

    if not args.submission.is_dir():
        print(f"error: submission dir not found: {args.submission}", file=sys.stderr)
        return 2
    try:
        print(json.dumps(grade(args.submission, args.unit, args.timeout)))
        return 0
    except Layer1Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
