"""Tests for active-rubric resolution (S1.6): the filesystem is the registry."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # platform/cli
from grader.rubric_version import (RubricResolutionError,  # noqa: E402
                                   resolve_active_rubric)


def make_versions(root: Path, unit: str, names: list[str]) -> Path:
    unit_dir = root / unit
    unit_dir.mkdir(parents=True)
    for name in names:
        (unit_dir / name).write_text("id: r\n")
    return root


def test_highest_version_wins_numerically(tmp_path: Path):
    make_versions(tmp_path, "0.1", ["v1.yaml", "v2.yaml", "v9.yaml", "v10.yaml"])
    active = resolve_active_rubric("0.1", rubrics_dir=tmp_path)
    assert active.name == "v10.yaml"  # numeric order, not lexicographic ("v10" < "v9")


def test_ignores_non_version_files(tmp_path: Path):
    make_versions(tmp_path, "0.1", ["v1.yaml", "v3.yaml", "notes.md", "rubric.yaml", "v2.yaml.bak"])
    active = resolve_active_rubric("0.1", rubrics_dir=tmp_path)
    assert active.name == "v3.yaml"


def test_missing_unit_dir_raises(tmp_path: Path):
    with pytest.raises(RubricResolutionError, match="no rubric directory"):
        resolve_active_rubric("9.9", rubrics_dir=tmp_path)


def test_dir_without_versioned_files_raises(tmp_path: Path):
    make_versions(tmp_path, "0.1", ["draft.yaml"])
    with pytest.raises(RubricResolutionError, match="no v<N>.yaml rubrics"):
        resolve_active_rubric("0.1", rubrics_dir=tmp_path)


def test_real_repo_rubric_resolves(tmp_path: Path):
    """The shipped unit 0.1 must resolve through the production default path."""
    active = resolve_active_rubric("0.1")
    assert active.name == "v1.yaml"
    assert active.is_file()
