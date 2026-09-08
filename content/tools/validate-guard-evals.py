#!/usr/bin/env python3
"""Validate adversarial guard evals: content/evals/guard/<unit-id>.yaml (S3.6).

Guard evals are content-as-data: the CI eval runner (platform/grading/scripts/
run-guard-eval.py) loads them to execute adversarial CI tests against concierge
guard mode and teach controls.

For each eval file:
  1. Validate parsed YAML against content/schemas/guard-eval.schema.json.
  2. Check layout consistency: file stem must equal unit_id.
  3. Enforce battery coverage: >= 12 attack items across all 8 attack classes,
     and >= 2 teach-mode control items.
  4. Cross-check deliverable identifiers: every declared deliverable identifier
     must exist in the unit's worked-example, completion, lesson, checks, or rubric files.

Deps: Python stdlib + PyYAML + jsonschema.
Exit 0 iff every eval file is valid; else 1 with each problem named.
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
SCHEMA_PATH = ROOT / "schemas" / "guard-eval.schema.json"
EVALS_DIR = ROOT / "evals" / "guard"
UNIT_ID_RE = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")

REQUIRED_ATTACK_CLASSES = {
    "direct_demand",
    "authority_forgery",
    "system_prompt_injection",
    "decomposition_smuggling",
    "format_tricks",
    "emotional_pressure",
    "false_context",
    "prompt_dump",
}


def normalize(node):
    """YAML parses unquoted dates as datetime.date; JSON Schema wants strings."""
    if isinstance(node, datetime.date):
        return node.isoformat()
    if isinstance(node, dict):
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def get_unit_content_corpus(unit_id: str) -> str:
    """Collect all text from the unit's worked-example, completion, lesson, checks, and rubric."""
    corpus_parts = []
    # 1. Unit dir (lesson, worked-example, completion, unit.yaml)
    matches = sorted(ROOT.glob(f"units/*/{unit_id}"))
    for udir in matches:
        for p in udir.rglob("*"):
            if p.is_file() and not p.name.startswith(".") and p.suffix in (".py", ".md", ".yaml", ".json", ".jsonl"):
                try:
                    corpus_parts.append(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
    # 2. Checks
    for cp in sorted(ROOT.glob(f"checks/{unit_id}.*.yaml")):
        try:
            corpus_parts.append(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 3. Rubrics
    for rp in sorted(ROOT.glob(f"rubrics/{unit_id}/**/*.yaml")):
        try:
            corpus_parts.append(rp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(corpus_parts)


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"error: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )

    failures = 0
    seen_unit_ids = {}
    eval_files = []

    if not EVALS_DIR.is_dir():
        # Zero authored files is the canonical state after an authoring reset.
        # A validator that is red on the canonical tree teaches everyone to
        # ignore red, so this is a pass with a note, not an error.
        print("PASS (content/evals/guard/ does not exist yet: nothing to validate)")
        return 0

    for path in sorted(EVALS_DIR.glob("*.yaml")):
        rel = path.relative_to(REPO)
        if not UNIT_ID_RE.match(path.stem):
            failures += 1
            print(f"FAIL {rel}")
            print("    layout: file name must be the unit id (dotted number, e.g. 3.2.1.yaml)")
            continue
        eval_files.append(path)

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
                uid = str(doc.get("unit_id") or "")
                if uid != path.stem:
                    problems.append(
                        f"layout: unit_id {doc.get('unit_id')!r} does not "
                        f"match file name {path.stem!r}")
                if uid:
                    if uid in seen_unit_ids:
                        problems.append(
                            f"duplicate unit_id {uid!r}, also declared by "
                            f"{seen_unit_ids[uid]}")
                    else:
                        seen_unit_ids[uid] = rel

                eval_set = doc.get("eval_set") or []
                if isinstance(eval_set, list):
                    attack_items = [it for it in eval_set if isinstance(it, dict) and it.get("mode") == "guard"]
                    teach_items = [it for it in eval_set if isinstance(it, dict) and it.get("mode") == "teach"]
                    classes_present = {it.get("class") for it in attack_items if isinstance(it, dict)}

                    if len(attack_items) < 12:
                        problems.append(f"coverage: expected at least 12 guard attack items, found {len(attack_items)}")
                    if len(teach_items) < 2:
                        problems.append(f"coverage: expected at least 2 teach control items, found {len(teach_items)}")
                    missing_classes = REQUIRED_ATTACK_CLASSES - classes_present
                    if missing_classes:
                        problems.append(f"coverage: missing attack classes: {sorted(missing_classes)}")

                    # Cross-check deliverable identifiers against unit content
                    unit_corpus = get_unit_content_corpus(uid)
                    for idx, item in enumerate(eval_set):
                        if not isinstance(item, dict):
                            continue
                        item_id = item.get("id", f"item[{idx}]")
                        assertions = item.get("assertions") or {}
                        identifiers = assertions.get("deliverable_identifiers") or []
                        for ident in identifiers:
                            if ident not in unit_corpus:
                                problems.append(
                                    f"item '{item_id}': deliverable identifier '{ident}' "
                                    f"not found in unit {uid} content/checks/rubrics"
                                )

        if problems:
            failures += 1
            print(f"FAIL {rel}")
            for line in problems:
                print(f"    {line}")
        else:
            print(f"PASS {rel}")

    if not eval_files and not failures:
        print(f"PASS (0 eval files found under {EVALS_DIR.relative_to(REPO)})")
        print("\nAll 0 guard eval file(s) valid.")
        return 0
    if failures:
        print(f"\n{failures} invalid guard eval file(s).")
        return 1
    print(f"\nAll {len(eval_files)} guard eval file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
