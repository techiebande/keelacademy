#!/usr/bin/env python3
"""Validate versioned rubrics: content/rubrics/<unit>/v<N>.yaml.

For each rubric:
  1. validate the parsed YAML against content/schemas/rubric.schema.json, and
  2. check filename/version-field consistency (v<N>.yaml must declare
     top-level `version: N`). The resolution rule (highest version is
     ACTIVE) depends on it.

Layout rule (S2.1): every .yaml under content/rubrics/ must live exactly one
level down (rubrics/<unit>/v<N>.yaml). A file at any other shape (top-level,
nested deeper, or not named v<N>.yaml) is a FAIL naming the file: it would
otherwise be silently unvalidated AND invisible to resolve_active_rubric.

Deps: Python stdlib + PyYAML only. The schema is interpreted by a small
validator supporting the keywords rubric.schema.json actually uses (type,
required, properties, items, additionalProperties, enum, pattern, minLength,
minimum, minItems), enough to keep this tool dependency-free.

Exit 0 iff every rubric is valid; else 1 with each failing file named.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent  # content/
REPO = ROOT.parent                              # repo root, for display
RUBRICS_DIR = ROOT / "rubrics"
SCHEMA_PATH = ROOT / "schemas" / "rubric.schema.json"
VERSION_RE = re.compile(r"^v(\d+)\.yaml$")


def schema_errors(node, schema: dict, path: str = "$") -> list[str]:
    """Errors of `node` against the supported subset of JSON Schema."""
    errors: list[str] = []
    t = schema.get("type")
    if t == "object":
        if not isinstance(node, dict):
            return [f"{path}: expected object, got {type(node).__name__}"]
        for key in schema.get("required", []):
            if key not in node:
                errors.append(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in node:
                if key not in props:
                    errors.append(f"{path}: additional property {key!r} not allowed")
        for key, sub in props.items():
            if key in node:
                errors.extend(schema_errors(node[key], sub, f"{path}.{key}"))
    elif t == "array":
        if not isinstance(node, list):
            return [f"{path}: expected array, got {type(node).__name__}"]
        if "minItems" in schema and len(node) < schema["minItems"]:
            errors.append(f"{path}: expected >= {schema['minItems']} items, got {len(node)}")
        for i, item in enumerate(node):
            errors.extend(schema_errors(item, schema.get("items", {}), f"{path}[{i}]"))
    elif t == "string":
        if not isinstance(node, str):
            return [f"{path}: expected string, got {type(node).__name__}"]
        if "minLength" in schema and len(node) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], node):
            errors.append(f"{path}: {node!r} does not match pattern {schema['pattern']!r}")
    elif t == "integer":
        if not isinstance(node, int) or isinstance(node, bool):
            return [f"{path}: expected integer, got {type(node).__name__}"]
        if "minimum" in schema and node < schema["minimum"]:
            errors.append(f"{path}: {node} < minimum {schema['minimum']}")
    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: {node!r} not in enum {schema['enum']}")
    return errors


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    rubric_files = []
    failures = 0
    for path in sorted(RUBRICS_DIR.glob("**/*.yaml")):
        rel = path.relative_to(REPO)
        if VERSION_RE.match(path.name) and path.parent.parent == RUBRICS_DIR:
            rubric_files.append(path)
            continue
        failures += 1
        reason = ("filename must be v<N>.yaml" if path.parent.parent == RUBRICS_DIR
                  else f"must live at rubrics/<unit>/v<N>.yaml, not {path.parent.relative_to(RUBRICS_DIR)}/")
        print(f"FAIL {rel}")
        print(f"    layout: {reason}. Unvalidated and invisible to the resolver")
    if not rubric_files and not failures:
        print(f"PASS (0 rubrics found under {RUBRICS_DIR.relative_to(REPO)})")
        print("\nAll 0 rubric file(s) valid.")
        return 0

    for path in rubric_files:
        rel = path.relative_to(REPO)
        problems: list[str] = []
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            problems.append(f"YAML parse error: {exc}")
            doc = None
        if isinstance(doc, dict):
            problems.extend(schema_errors(doc, schema))
            m = VERSION_RE.match(path.name)
            if doc.get("version") != int(m.group(1)):
                problems.append(
                    f"filename/version mismatch: {path.name} declares version "
                    f"{doc.get('version')!r}, expected {m.group(1)}")
        elif doc is None and not problems:
            problems.append("file is empty or parses to null")
        elif doc is not None:
            problems.append(f"expected a mapping at top level, got {type(doc).__name__}")

        if problems:
            failures += 1
            print(f"FAIL {rel}")
            for p in problems:
                print(f"    {p}")
        else:
            print(f"PASS {rel}")

    if failures:
        print(f"\n{failures} invalid rubric file(s).")
        return 1
    print(f"\nAll {len(rubric_files)} rubric file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
