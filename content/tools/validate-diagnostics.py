#!/usr/bin/env python3
"""Validate diagnostic assessments and commitment declarations (S4.1).

Validates:
1. content/commitment/*.yaml against content/schemas/commitment.schema.json
2. content/diagnostic/*.yaml against content/schemas/diagnostic.schema.json

Cross-checks for diagnostics:
- Every question category must match a declared category id.
- Every question correct_answer must match an option id within that question.
- Question point values and category weights must be valid.
- Threshold percentage must be between 0 and 100.

Deps: Python stdlib + PyYAML + jsonschema.
Exit 0 if valid; 1 on any failure naming the file and error.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent  # content/
REPO = ROOT.parent                              # repo root, for display
SCHEMAS_DIR = ROOT / "schemas"
COMMITMENT_DIR = ROOT / "commitment"
DIAGNOSTIC_DIR = ROOT / "diagnostic"

COMMITMENT_SCHEMA = SCHEMAS_DIR / "commitment.schema.json"
DIAGNOSTIC_SCHEMA = SCHEMAS_DIR / "diagnostic.schema.json"


def normalize(node: Any) -> Any:
    if isinstance(node, datetime.date):
        return node.isoformat()
    if isinstance(node, dict):
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    rendered = []
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "<root>"
        rendered.append(f"{loc}: {err.message}")
    return rendered


def validate_diagnostic_semantics(doc: dict[str, Any]) -> list[str]:
    errors = []
    categories = doc.get("categories") or []
    cat_ids = {c.get("id") for c in categories if isinstance(c, dict)}
    
    questions = doc.get("questions") or []
    for idx, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qid = q.get("id", f"questions[{idx}]")
        cat = q.get("category")
        if cat not in cat_ids:
            errors.append(f"question '{qid}': category '{cat}' is not in declared categories {sorted(cat_ids)}")
        
        options = q.get("options") or []
        opt_ids = {opt.get("id") for opt in options if isinstance(opt, dict)}
        correct = q.get("correct_answer")
        if correct not in opt_ids:
            errors.append(f"question '{qid}': correct_answer '{correct}' is not among option ids {sorted(opt_ids)}")
            
    return errors


def main() -> int:
    failures = 0

    if not COMMITMENT_SCHEMA.is_file():
        print(f"error: schema not found at {COMMITMENT_SCHEMA}", file=sys.stderr)
        return 1
    if not DIAGNOSTIC_SCHEMA.is_file():
        print(f"error: schema not found at {DIAGNOSTIC_SCHEMA}", file=sys.stderr)
        return 1

    commit_schema = json.loads(COMMITMENT_SCHEMA.read_text(encoding="utf-8"))
    diag_schema = json.loads(DIAGNOSTIC_SCHEMA.read_text(encoding="utf-8"))

    # 1. Validate commitment files
    commit_files = sorted(COMMITMENT_DIR.glob("*.yaml")) if COMMITMENT_DIR.is_dir() else []
    if not commit_files:
        print("error: no commitment files found in content/commitment/", file=sys.stderr)
        failures += 1
    for cp in commit_files:
        rel = cp.relative_to(REPO)
        problems = []
        try:
            doc = yaml.safe_load(cp.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"YAML parse error: {exc}")
            doc = None
        if doc is None and not problems:
            problems.append("file is empty or parses to null")
        elif isinstance(doc, dict):
            problems.extend(schema_errors(normalize(doc), commit_schema))
        if problems:
            failures += 1
            print(f"FAIL {rel}")
            for p in problems:
                print(f"    {p}")
        else:
            print(f"PASS {rel}")

    # 2. Validate diagnostic files
    diag_files = sorted(DIAGNOSTIC_DIR.glob("*.yaml")) if DIAGNOSTIC_DIR.is_dir() else []
    if not diag_files:
        print("error: no diagnostic files found in content/diagnostic/", file=sys.stderr)
        failures += 1
    for dp in diag_files:
        rel = dp.relative_to(REPO)
        problems = []
        try:
            doc = yaml.safe_load(dp.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"YAML parse error: {exc}")
            doc = None
        if doc is None and not problems:
            problems.append("file is empty or parses to null")
        elif isinstance(doc, dict):
            problems.extend(schema_errors(normalize(doc), diag_schema))
            problems.extend(validate_diagnostic_semantics(doc))
        if problems:
            failures += 1
            print(f"FAIL {rel}")
            for p in problems:
                print(f"    {p}")
        else:
            print(f"PASS {rel}")

    if failures:
        print(f"\n{failures} invalid file(s). See FAIL lines above.")
        return 1
    print("\nAll commitment and diagnostic content valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
