#!/usr/bin/env python3
"""Validate the content repo against the JSON schemas in content/schemas/.

Two kinds of cases:

  1. Fixture examples under content/examples/. Valid ones must PASS and
      *.invalid.yaml must FAIL (proves the schemas reject bad content).
  2. Discovered real content. Every file must PASS:
       content/units/**/unit.yaml    vs unit.schema.json
       content/variants/*.yaml       vs variant.schema.json   (may be empty)
       content/personas/*.yaml       vs persona.schema.json   (may be empty)
     Real rubrics are owned by validate-rubrics.py, which additionally
     checks filename/version consistency.

Discovered unit files carry two layout-consistency rules (S2.1):
  - the enclosing directory name must equal the unit's `id`
    (content/units/phase-3/3.2.1/unit.yaml declares id: "3.2.1")
  - if the directory above that matches phase-<N>, it must equal the
    unit's `phase` field
These make the on-disk layout load-bearing: a unit cannot validate under
a path that disagrees with its own identity.

A discovered file that does not parse as YAML is a FAIL naming the file.
The validator never crashes on bad input.

Prints PASS/FAIL per file (paths relative to the repo root); exits 1 if
any result is unexpected, with every offending file named.
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
SCHEMAS = ROOT / "schemas"

# (schema, instance path relative to repo root, must_pass)
FIXTURE_CASES = [
    # S0.1 example instances
    ("unit.schema.json", "content/examples/unit.example.yaml", True),
    ("rubric.schema.json", "content/examples/rubric.example.yaml", True),
    ("variant.schema.json", "content/examples/variant.example.yaml", True),
    ("persona.schema.json", "content/examples/persona.example.yaml", True),
    ("map.schema.json", "content/examples/map.example.yaml", True),
    ("routing.schema.json", "content/examples/routing.example.yaml", True),
    ("guard-eval.schema.json", "content/examples/guard-eval.example.yaml", True),
    ("commitment.schema.json", "content/examples/commitment.example.yaml", True),
    ("diagnostic.schema.json", "content/examples/diagnostic.example.yaml", True),
    ("unit.schema.json", "content/examples/unit-conceptual.example.yaml", True),
    ("unit.schema.json", "content/examples/unit.invalid.yaml", False),
    ("unit.schema.json", "content/examples/unit-conceptual.invalid.yaml", False),
    ("routing.schema.json", "content/examples/routing.invalid.yaml", False),
    ("guard-eval.schema.json", "content/examples/guard-eval.invalid.yaml", False),
    ("commitment.schema.json", "content/examples/commitment.invalid.yaml", False),
    ("diagnostic.schema.json", "content/examples/diagnostic.invalid.yaml", False),
]

# (schema, glob relative to content/, may_be_empty)
DISCOVERED = [
    ("unit.schema.json", "units/**/unit.yaml", True),
    ("map.schema.json", "curriculum/phases.yaml", False),
    ("ledger.schema.json", "curriculum/ledger.yaml", True),
    ("variant.schema.json", "variants/*.yaml", True),
    ("persona.schema.json", "personas/*.yaml", True),
    ("guard-eval.schema.json", "evals/guard/*.yaml", True),
    ("commitment.schema.json", "commitment/*.yaml", False),
    ("diagnostic.schema.json", "diagnostic/*.yaml", False),
]

PHASE_DIR_RE = re.compile(r"^phase-(\d+)$")


def normalize(node):
    """YAML parses unquoted dates as datetime.date; JSON Schema wants strings."""
    if isinstance(node, datetime.date):
        return node.isoformat()
    if isinstance(node, dict):
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def repo_rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


def schema_errors(instance, schema: dict) -> list[str]:
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    rendered = []
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "<root>"
        rendered.append(f"{loc}: {err.message}")
    return rendered


def unit_layout_errors(doc, path: Path) -> list[str]:
    """Layout-consistency rules for a discovered unit file."""
    if not isinstance(doc, dict):
        return []  # schema errors already cover non-mapping documents
    errors = []
    if "id" in doc and str(doc["id"]) != path.parent.name:
        errors.append(
            f"layout: unit id {doc['id']!r} does not match its directory "
            f"{path.parent.name!r}"
        )
    m = PHASE_DIR_RE.match(path.parent.parent.name)
    if m and doc.get("phase") != int(m.group(1)):
        errors.append(
            f"layout: phase {doc.get('phase')!r} does not match its directory "
            f"{path.parent.parent.name!r}"
        )
    return errors


def main() -> int:
    failures = 0

    for schema_name, instance_path, must_pass in FIXTURE_CASES:
        schema = load_schema(schema_name)
        instance = normalize(
            yaml.safe_load((REPO / instance_path).read_text())
        )
        errors = schema_errors(instance, schema)
        passed = not errors
        ok = passed == must_pass
        failures += not ok
        status = "PASS" if passed else "FAIL"
        print(f"{instance_path} vs {schema_name} [{status}]"
              f"{'  (expected invalid)' if not must_pass else ''}"
              f"{'' if ok else '  << UNEXPECTED'}")
        for line in errors:
            print(f"    {line}")

    for schema_name, pattern, may_be_empty in DISCOVERED:
        schema = load_schema(schema_name)
        found = sorted(ROOT.glob(pattern))
        if not found and not may_be_empty:
            print(f"\nerror: no files match content/{pattern}", file=sys.stderr)
            failures += 1
            continue
        for path in found:
            problems: list[str] = []
            try:
                doc = yaml.safe_load(path.read_text())
            except yaml.YAMLError as exc:
                problems.append(f"YAML parse error: {exc}")
                doc = None
            if doc is None and not problems:
                problems.append("file is empty or parses to null")
            else:
                problems.extend(schema_errors(normalize(doc), schema))
            if schema_name == "unit.schema.json":
                problems.extend(unit_layout_errors(doc, path))
            if problems:
                failures += 1
                print(f"FAIL {repo_rel(path)}")
                for line in problems:
                    print(f"    {line}")
            else:
                print(f"PASS {repo_rel(path)}")

    if failures:
        print(f"\n{failures} invalid or unexpected file(s). See FAIL lines above.")
        return 1
    print("\nAll results as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
