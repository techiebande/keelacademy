"""Versioned-rubric resolution.

Rubrics live at content/rubrics/<unit_id>/v<N>.yaml. The highest version
number in the directory is the ACTIVE rubric for that unit — no registry, no
symlinks; the filesystem is the source of truth. Callers that need an exact
historical version (calibrate, gate) pass an explicit path; this resolver is
for anything that wants "the current rubric" (S1.6).
"""
from __future__ import annotations

import re
from pathlib import Path

# Repo layout: platform/cli/grader/rubric_version.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUBRICS_DIR = REPO_ROOT / "content" / "rubrics"

VERSION_RE = re.compile(r"^v(\d+)\.yaml$")


class RubricResolutionError(Exception):
    pass


def resolve_active_rubric(unit_id: str, rubrics_dir: Path | None = None) -> Path:
    """Return the path of the ACTIVE (highest-numbered) rubric for unit_id."""
    root = Path(rubrics_dir) if rubrics_dir else DEFAULT_RUBRICS_DIR
    unit_dir = root / unit_id
    if not unit_dir.is_dir():
        raise RubricResolutionError(f"no rubric directory for unit {unit_id!r} under {root}")
    versions = sorted(
        (int(m.group(1)), p)
        for p in unit_dir.iterdir()
        if p.is_file() and (m := VERSION_RE.match(p.name))
    )
    if not versions:
        raise RubricResolutionError(f"no v<N>.yaml rubrics in {unit_dir}")
    return versions[-1][1]


if __name__ == "__main__":
    # Minimal CLI for orchestrators (the S1.8 worker): print the active rubric
    # path for a unit so callers never re-implement the resolution rule.
    import sys

    try:
        print(resolve_active_rubric(sys.argv[1]))
    except (IndexError, RubricResolutionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
