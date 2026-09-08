#!/usr/bin/env python3
"""Validate gate rules: content/gates/<gate-id>.yaml (S2.7).

Gate rules are content-as-data: the gate engine (platform/grading/gates/
engine.py) loads them to decide which verdicts it evaluates and what they
unlock. For each rule file:

  1. validate the parsed YAML against content/schemas/gate.schema.json, and
  2. check layout consistency. The file name stem must equal the gate_id.

Cross-file rules (the engine depends on both):
  - no two rules may declare the same gate_id (a pledge or passage event
    names a gate; duplicates would make the rule set ambiguous), and
  - no two rules may declare the same unit_id (a verdict on a unit must
    satisfy at most one gate; the engine indexes rules by unit).

A file under content/gates/ that is not <gate-id>.yaml is a FAIL naming the
file, mirroring the rubric layout rule. A YAML parse error is a FAIL naming
the file; the validator never crashes on bad input.

Deps: Python stdlib + PyYAML + jsonschema (same as validate.py).

Exit 0 iff every rule file is valid; else 1 with each failing file named.
"""
import datetime
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent  # content/
REPO = ROOT.parent                              # repo root, for display
SCHEMA_PATH = ROOT / "schemas" / "gate.schema.json"
GATES_DIR = ROOT / "gates"
GATE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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
    seen_gate_ids = {}
    seen_unit_ids = {}
    rule_files = []

    if not GATES_DIR.is_dir():
        print("error: content/gates/ does not exist", file=sys.stderr)
        return 1
    for path in sorted(GATES_DIR.glob("*.yaml")):
        rel = path.relative_to(REPO)
        if not GATE_ID_RE.match(path.stem):
            failures += 1
            print(f"FAIL {rel}")
            print("    layout: file name must be the gate id (lowercase slug)")
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
                if str(doc.get("gate_id", "")) != path.stem:
                    problems.append(
                        f"layout: gate_id {doc.get('gate_id')!r} does not "
                        f"match file name {path.stem!r}")
                gid = str(doc.get("gate_id") or "")
                uid = str(doc.get("unit_id") or "")
                if gid:
                    if gid in seen_gate_ids:
                        problems.append(
                            f"duplicate gate_id {gid!r}, also declared by "
                            f"{seen_gate_ids[gid]}")
                    else:
                        seen_gate_ids[gid] = rel
                if uid:
                    if uid in seen_unit_ids:
                        problems.append(
                            f"duplicate unit_id {uid!r}, also gated by "
                            f"{seen_unit_ids[uid]}. A verdict must satisfy "
                            f"at most one gate")
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
        print("error: no rule files found under content/gates/", file=sys.stderr)
        return 1
    if failures:
        print(f"\n{failures} invalid gate rule file(s).")
        return 1
    print(f"\nAll {len(rule_files)} gate rule file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
