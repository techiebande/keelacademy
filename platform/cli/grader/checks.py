"""Loading and validation of check files in the {id, type, run, expect} format.

Observed expect forms (from content/checks/):
  exit_zero                  pass iff container exit code == 0
  exit_nonzero               pass iff container exit code != 0
  {output_contains: <str>}   pass iff <str> appears in the check's stdout/stderr
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

VALID_TYPES = {"pytest", "command"}


@dataclass
class Check:
    id: str
    type: str
    run: str
    expect: str | dict


def load_checks(path: Path) -> list[Check]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of checks")
    checks = []
    for i, item in enumerate(raw):
        missing = {"id", "type", "run", "expect"} - set(item)
        if missing:
            raise ValueError(f"{path}: check #{i} missing keys {sorted(missing)}")
        if item["type"] not in VALID_TYPES:
            raise ValueError(f"{path}: check {item['id']!r} has unknown type {item['type']!r}")
        checks.append(Check(id=item["id"], type=item["type"], run=item["run"], expect=item["expect"]))
    return checks


def evaluate_expect(expect: str | dict, exit_code: int | None, output: str) -> tuple[bool, str]:
    """Return (passed, human note). exit_code None means the check errored (timeout etc.)."""
    if exit_code is None:
        return False, "error before exit"
    if expect == "exit_zero":
        return exit_code == 0, f"exit code {exit_code}"
    if expect == "exit_nonzero":
        return exit_code != 0, f"exit code {exit_code}"
    if isinstance(expect, dict) and "output_contains" in expect:
        found = expect["output_contains"] in output
        return found, f"output {'contains' if found else 'lacks'} {expect['output_contains']!r}"
    raise ValueError(f"unsupported expect: {expect!r}")


def remap_run_paths(run: str, submission_dir: Path) -> str:
    """Rewrite path tokens in `run` that don't resolve inside the submission.

    Some check files (e.g. content/checks/3.2.1.completion.yaml) write paths
    relative to the content/ repo root (`units/phase-3/3.2.1/completion/...`)
    while the submission dir is that subtree itself. For any token containing a
    "/" that does not exist relative to the submission, try progressively
    shorter suffixes of the path; the first suffix that exists (or "." when the
    path names the submission root itself) replaces the token.
    """
    try:
        tokens = shlex.split(run)
    except ValueError:
        return run  # odd quoting; leave untouched, the shell in the container decides
    out = []
    for tok in tokens:
        out.append(_remap_token(tok, submission_dir))
    return shlex.join(out)


def _remap_token(tok: str, submission_dir: Path) -> str:
    if "/" not in tok or tok.startswith("-"):
        return tok
    candidate = PurePosixPath(tok.rstrip("/"))
    if (submission_dir / candidate).exists():
        return tok
    parts = candidate.parts
    for i in range(1, len(parts)):
        suffix = PurePosixPath(*parts[i:])
        if (submission_dir / suffix).exists():
            return str(suffix)
    # No suffix exists. A trailing slash means the token names a directory — if
    # it plausibly names the submission root itself (".../completion/"), use the
    # mount point. Otherwise leave the token alone; the container will report
    # the missing file honestly.
    if tok.endswith("/"):
        return "."
    return tok
