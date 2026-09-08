#!/usr/bin/env python3
"""Validate curriculum map skeleton: content/curriculum/phases.yaml (S2.8).

The curriculum map is content-as-data: the progress dashboard renders the
13-phase OmniCart pipeline directly from this skeleton joined with authored
units in content/units/ and gate rules in content/gates/.

Checks:
  1. Validate parsed YAML against content/schemas/map.schema.json
  2. Phase order: exactly 13 phases (0..12) in ascending numeric order
  3. Gate consistency: any gate_id referenced must exist in content/gates/<gate-id>.yaml
  4. Unit consistency: every authored unit in content/units/ must be declared in the map

Deps: Python stdlib + PyYAML + jsonschema (same as validate.py).
Exit 0 iff valid; else 1 with failures named.
"""
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent  # content/
REPO = ROOT.parent                              # repo root, for display
SCHEMA_PATH = ROOT / "schemas" / "map.schema.json"
CURRICULUM_PATH = ROOT / "curriculum" / "phases.yaml"
GATES_DIR = ROOT / "gates"
UNITS_DIR = ROOT / "units"


def normalize(node):
    if isinstance(node, dict):
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"error: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1
    if not CURRICULUM_PATH.is_file():
        print(f"error: curriculum file not found at {CURRICULUM_PATH}", file=sys.stderr)
        return 1

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )

    rel = CURRICULUM_PATH.relative_to(REPO)
    problems = []

    try:
        doc = yaml.safe_load(CURRICULUM_PATH.read_text())
    except yaml.YAMLError as exc:
        print(f"FAIL {rel}")
        print(f"    YAML parse error: {exc}")
        return 1

    if doc is None or not isinstance(doc, dict):
        print(f"FAIL {rel}")
        print("    file is empty or not a mapping")
        return 1

    errors = sorted(validator.iter_errors(normalize(doc)), key=lambda e: list(e.path))
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "<root>"
        problems.append(f"{loc}: {err.message}")

    phases = doc.get("phases", [])
    all_module_ids = set()
    if isinstance(phases, list):
        if len(phases) != 13:
            problems.append(f"expected exactly 13 phases (0..12), found {len(phases)}")
        for idx, p in enumerate(phases):
            if not isinstance(p, dict):
                continue
            phase_num = p.get("phase")
            if phase_num != idx:
                problems.append(f"phases[{idx}]: phase number {phase_num} does not equal index {idx}")
            expected_id = f"phase-{idx}"
            if p.get("id") != expected_id:
                problems.append(f"phases[{idx}]: id {p.get('id')!r} does not match expected {expected_id!r}")
            gid = p.get("gate_id")
            if gid:
                gate_file = GATES_DIR / f"{gid}.yaml"
                if not gate_file.is_file():
                    problems.append(f"phases[{idx}]: gate_id {gid!r} has no corresponding rule file at content/gates/{gid}.yaml")
            for m in p.get("modules", []):
                if isinstance(m, dict) and "id" in m:
                    mid = str(m["id"])
                    if mid in all_module_ids:
                        problems.append(f"duplicate module id {mid!r} in curriculum map")
                    all_module_ids.add(mid)

        # Check that authored units in content/units/ match modules declared in map
        if UNITS_DIR.is_dir():
            for phase_dir in UNITS_DIR.glob("phase-*"):
                for unit_yaml in phase_dir.glob("*/unit.yaml"):
                    unit_id = unit_yaml.parent.name
                    if unit_id not in all_module_ids:
                        problems.append(f"authored unit {unit_id} ({unit_yaml.relative_to(REPO)}) is not declared in curriculum map")

    if problems:
        print(f"FAIL {rel}")
        for p in problems:
            print(f"    {p}")
        return 1

    print(f"PASS {rel}")
    print(f"\nCurriculum map valid (13 phases, {len(all_module_ids)} modules).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
