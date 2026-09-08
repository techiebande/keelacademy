#!/usr/bin/env python3
"""Print only one unit's section of curriculum.md.

curriculum.md is 86 KB of reference material. Authoring agents need just the
target unit's slice (improvement plan M3.2), so the orchestrator hands them
this output instead of the whole file.

Usage: python3 content/tools/curriculum-section.py <unit-id>
Example: python3 content/tools/curriculum-section.py 0.1
Exit 0 and the section on stdout; exit 1 with a message if the unit has no
heading in curriculum.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CURRICULUM = Path(__file__).resolve().parent.parent.parent / "curriculum.md"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    unit_id = sys.argv[1].strip()
    if not re.fullmatch(r"\d+\.\d+(\.\d+)?", unit_id):
        print(f"FAIL '{unit_id}' is not a unit id (expected shapes: 0.1, 3.2.1)", file=sys.stderr)
        return 2

    lines = CURRICULUM.read_text(encoding="utf-8").splitlines()
    heading_re = re.compile(r"^(#{2,4}) (\d[\d.]*)\s")

    start = None
    start_level = 0
    for i, line in enumerate(lines):
        m = heading_re.match(line)
        if m and m.group(2) == unit_id:
            start, start_level = i, len(m.group(1))
            break
    if start is None:
        print(f"FAIL no heading for unit {unit_id} in curriculum.md", file=sys.stderr)
        return 1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        m = heading_re.match(lines[i])
        if m and len(m.group(1)) <= start_level:
            end = i
            break

    print("\n".join(lines[start:end]).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
