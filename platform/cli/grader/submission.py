"""Shared submission reading: render a submission's files as text (never execute)."""
from __future__ import annotations

from pathlib import Path

# Submission files the model must never see (answers / noise).
EXCLUDE_FILES = {"grade.yaml", "claims_messy.jsonl"}
EXCLUDE_DIRS = {"__pycache__", ".git", ".venv"}

ALLOWED_SUFFIXES = {".py", ".jsonl", ".log", ".txt", ".md", ".json", ".yaml"}


class SubmissionError(Exception):
    pass


def gather_submission(submission_dir: Path) -> str:
    """Render the submission's files per the checks-file layout contract:
    extract_claims.py, tests/, and any run artifacts (out.jsonl, run.log) —
    i.e. everything except grader answers and data fixtures."""
    parts = []
    for path in sorted(submission_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDE_FILES or any(p in EXCLUDE_DIRS for p in path.parts):
            continue
        if path.suffix not in ALLOWED_SUFFIXES:
            continue
        rel = path.relative_to(submission_dir)
        body = path.read_text(errors="replace")
        parts.append(f"----- FILE: {rel.as_posix()} -----\n{body}")
    if not parts:
        raise SubmissionError(f"no readable files found in {submission_dir}")
    return "\n\n".join(parts)
