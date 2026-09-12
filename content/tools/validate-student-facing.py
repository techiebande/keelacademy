#!/usr/bin/env python3
"""Reject private repository details from student-facing unit prose.

Student-facing files are the lesson chapters and assignment.md files. Students
see those files through the product, not the source repository. This check is a
boundary check, not a style checker: it blocks source paths, internal agent
paths, absolute sandbox paths, and explicit instructions to open private repo
files. It does not ban normal course-folder paths such as `client-brief.md` or
`messages/M-1041.txt`, because those are artifacts the assignment can provide.

Exit 0 when all authored units pass; exit 1 with file and line diagnostics.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "content" / "units"

# Source-only namespaces and path shapes. Keep this list about access boundaries,
# not vocabulary: technical words and ordinary filenames are valid in lessons.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("repository content path", re.compile(r"(?<![\w`])content/(?:client|units|rubrics|prompts|schemas|tools|gates|golden)(?:/|\b)", re.I)),
    ("repository platform path", re.compile(r"(?<![\w`])platform/(?:app|grading|cli)(?:/|\b)", re.I)),
    ("repository agent path", re.compile(r"(?<![\w`])\.agents/(?:agents|skills|rules)(?:/|\b)", re.I)),
    ("repository documentation path", re.compile(r"(?<![\w`])(?:docs|scratch|\.github|\.githooks)/[A-Za-z0-9_.-]+", re.I)),
    ("absolute local path", re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\\\)", re.I)),
    ("source-file access instruction", re.compile(r"\b(?:read|open|look at|find|copy|inspect|see)\s+(?:the|your)?\s*(?:source|repo|repository|codebase|private)\s+(?:file|folder|directory|path)", re.I)),
    ("internal implementation instruction", re.compile(r"\b(?:read|open|look at|inspect)\s+(?:unit\.yaml|package\.json|AGENTS\.md|README\.md|build-state\.md|school-architecture\.md|build-plan\.md)\b", re.I)),
]


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for label, pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(line)
            if match:
                errors.append(f"{path.relative_to(ROOT)}:{number}: {label}: {match.group(0)!r}")
    return errors


def main() -> int:
    files = sorted(UNITS.glob("phase-*/*/lesson*.md"))
    files += sorted(UNITS.glob("phase-*/*/assignment.md"))
    errors = [error for path in files for error in check_file(path)]
    if errors:
        print("Student-facing boundary check failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Student-facing boundary check passed ({len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _test_patterns() -> None:
    """Small no-dependency regression checks for the boundary itself."""
    assert any(pattern.search("Read content/client/brief.md") for _, pattern in FORBIDDEN_PATTERNS)
    assert any(pattern.search("Open platform/app/lib/content.ts") for _, pattern in FORBIDDEN_PATTERNS)
    assert not any(pattern.search("Save as client-brief.md") for _, pattern in FORBIDDEN_PATTERNS)
    assert not any(pattern.search("Open messages/M-1041.txt") for _, pattern in FORBIDDEN_PATTERNS)
