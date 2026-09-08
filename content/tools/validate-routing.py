#!/usr/bin/env python3
"""Validate adaptive routing rules: content/routing/<unit-id>.yaml (S3.4).

Routing rules are content-as-data: the practice service (platform/grading/practice/
server.py) loads them to compute adaptive practice routes per student.
For each rule file:

  1. validate the parsed YAML against content/schemas/routing.schema.json, and
  2. check layout consistency. The file name stem must equal the unit_id.

Cross-file rules:
  - no two rules may declare the same unit_id.

A file under content/routing/ that is not <unit-id>.yaml is a FAIL naming the
file. A YAML parse error is a FAIL naming the file; the validator never crashes
on bad input.

Deps: Python stdlib + PyYAML + jsonschema (same as validate-gates.py).

Exit 0 iff every rule file is valid; else 1 with each failing file named.
"""
import datetime
import json
import os
import re
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent  # content/
REPO = ROOT.parent                              # repo root, for display
SCHEMA_PATH = ROOT / "schemas" / "routing.schema.json"
ROUTING_DIR = ROOT / "routing"
UNIT_ID_RE = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")


def normalize(node):
    """YAML parses unquoted dates as datetime.date; JSON Schema wants strings."""
    if isinstance(node, datetime.date):
        return node.isoformat()
    if isinstance(node, dict):
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )

    failures = 0
    seen_unit_ids = {}
    rule_files = []

    if not ROUTING_DIR.is_dir():
        # Zero authored files is the canonical state after an authoring reset
        # (M4.2): the practice service treats that as "no adaptive route for
        # this unit". A validator that is red on the canonical tree teaches
        # everyone to ignore red, so this is a pass with a note, not an error.
        print("PASS (content/routing/ does not exist yet: nothing to validate)")
        print("\nAll 0 routing rule file(s) valid.")
        return 0
    for path in sorted(ROUTING_DIR.glob("*.yaml")):
        rel = path.relative_to(REPO)
        if not UNIT_ID_RE.match(path.stem):
            failures += 1
            print(f"FAIL {rel}")
            print("    layout: file name must be the unit id (dotted number, e.g. 3.2.1.yaml)")
            continue
        rule_files.append(path)

        problems = []
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            problems.append(f"YAML parse error: {exc}")
            doc = None
        if doc is None and not problems:
            problems.append("file is empty or parses to null")
        else:
            errors = sorted(validator.iter_errors(normalize(doc)),
                            key=lambda e: list(e.path))
            for err in errors:
                loc = "/".join(str(p) for p in err.path) or "<root>"
                problems.append(f"{loc}: {err.message}")
            if isinstance(doc, dict):
                if str(doc.get("unit_id", "")) != path.stem:
                    problems.append(
                        f"layout: unit_id {doc.get('unit_id')!r} does not "
                        f"match file name {path.stem!r}")
                uid = str(doc.get("unit_id") or "")
                if uid:
                    if uid in seen_unit_ids:
                        problems.append(
                            f"duplicate unit_id {uid!r}, also declared by "
                            f"{seen_unit_ids[uid]}")
                    else:
                        seen_unit_ids[uid] = rel

        if problems:
            failures += 1
            print(f"FAIL {rel}")
            for line in problems:
                print(f"    {line}")
        else:
            print(f"PASS {rel}")

    if not rule_files and not failures:
        print(f"PASS (0 rule files found under {ROUTING_DIR.relative_to(REPO)})")
        print("\nAll 0 routing rule file(s) valid.")
        return 0
    if failures:
        print(f"\n{failures} invalid routing rule file(s).")
        return 1
    print(f"\nAll {len(rule_files)} routing rule file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
