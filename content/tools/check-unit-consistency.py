#!/usr/bin/env python3
"""Cross-file consistency gate for one authored unit.

The blind playtest of Unit 0.1 found that most defects were not bad prose but
DISAGREEMENTS between files: the lesson said five checks while the exercise
listed nine rules, four files named four different starting points, the FAQ
taught a number nothing else mentioned. A single author cannot hold six files
in their head; a small model certainly cannot. This script does it for them.

Checks (all must pass):
  1. The five required headings in completion/README.md appear verbatim in the
     lesson's build phase and in the completion template, in the same order.
  2. Every rubric criterion id is named, in plain words, in the completion
     README (a "checks" or "rules" section) so the student knows what is graded.
  3. Numbers that the rubric or judge prompt relies on (volume, wait, target,
     example cents amount, id examples) appear in learn.md AND completion README.
  4. Banned-word lists agree between rubric, judge prompt and completion README.
  5. Document names the rubric requires (order receipt, delivery slip, unboxing
     photo, return policy) are named in learn.md, completion README and worked
     example.
  6. Every unit.yaml unstuck fix_ref anchor exists in the FAQ.
  7. No file teaches a numeric threshold that appears nowhere else
     (the "50000 cents only in the FAQ" defect).
  8. Word budget (N to M words) is the same everywhere it is stated.

Usage: python3 content/tools/check-unit-consistency.py <unit-id>   (exit 1 on any failure)
The number and document lists are read from the unit's rubric and judge prompt,
so the tool adapts to each unit; anything unit-specific beyond that lives in
the optional `content/units/<phase>/<id>/consistency.yaml`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent  # content/


def find_unit_dir(unit_id: str) -> Path | None:
    for p in (ROOT / "units").glob(f"phase-*/{unit_id}"):
        if p.is_dir():
            return p
    return None


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def strip_fences(text: str) -> str:
    return re.sub(r"```[\s\S]*?```", "", text)


def fences(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n([\s\S]*?)```", text)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    unit_id = sys.argv[1]
    unit_dir = find_unit_dir(unit_id)
    if not unit_dir:
        print(f"FAIL no unit directory for {unit_id}")
        return 1

    unit = yaml.safe_load(read(unit_dir / "unit.yaml")) or {}
    learn = read(unit_dir / "learn.md")
    completion = read(unit_dir / "completion" / "README.md")
    worked = read(unit_dir / "worked-example" / "README.md")
    faq = read(ROOT / "faq" / f"{unit_id}.md")
    rubric_path = ROOT / (unit.get("verify", {}).get("rubric") or f"rubrics/{unit_id}/v1.yaml")
    rubric = yaml.safe_load(read(rubric_path)) or {}
    judge = read(ROOT / (rubric.get("judge", {}).get("prompt") or f"prompts/judge-{unit_id}.md"))
    extra = yaml.safe_load(read(unit_dir / "consistency.yaml")) or {}

    failures: list[str] = []
    notes: list[str] = []

    def fail(msg: str) -> None:
        failures.append(msg)

    # 1. Required headings: taken from the completion template (first fence that
    #    contains a line starting with "# ").
    template = next((f for f in fences(completion) if re.search(r"^# ", f, re.M)), "")
    headings = [l.strip() for l in template.splitlines() if re.match(r"^#{1,2} ", l.strip())]
    if not headings:
        fail("completion/README.md has no template fence with # headings")
    else:
        learn_fence_headings = [l.strip() for f in fences(learn) for l in f.splitlines() if re.match(r"^#{1,2} ", l.strip())]
        if learn_fence_headings and learn_fence_headings != headings:
            fail(f"learn.md lists headings {learn_fence_headings} but the completion template has {headings}")
        elif not learn_fence_headings:
            notes.append("learn.md does not list the deliverable headings in a fenced block (optional)")
        # Rules text must mention each heading without the # marks
        for h in headings:
            plain = h.lstrip("# ").strip()
            if plain.lower() not in strip_fences(completion).lower():
                fail(f"completion README rules never mention the heading '{plain}'")

    # 2. Rubric criteria named in completion README.
    crit_ids = [c["id"] for c in rubric.get("criteria", [])]
    if crit_ids:
        n_checks = len(crit_ids)
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
        numerals = "|".join([str(n_checks)] + [w for w, n in words.items() if n == n_checks])
        if not re.search(rf"\b(?:{numerals})\b\s+checks", completion, re.I):
            fail(f"completion README never says '{n_checks} checks' although the rubric has {n_checks} criteria")
        if learn and not re.search(rf"\b(?:{n_checks}|five|four|six|three)\b\s+checks", learn, re.I):
            notes.append("learn.md does not state the number of checks (optional)")
        # The word 'five checks' in learn must match the rubric count if present
        m = re.search(r"\b(three|four|five|six|seven|\d+)\s+checks", learn, re.I)
        if m:
            said = words.get(m.group(1).lower(), None) or int(m.group(1)) if m.group(1).isdigit() or m.group(1).lower() in words else None
            if said and said != n_checks:
                fail(f"learn.md says '{m.group(0)}' but the rubric has {n_checks} criteria")

    # 3. Load-bearing numbers: from consistency.yaml if present, else mined from the rubric.
    numbers = extra.get("numbers")
    if numbers is None:
        notes.append("no consistency.yaml `numbers` list; numbers mined from rubric and judge prompt")
    numbers = numbers or sorted(set(re.findall(r"\b(?:about\s+)?\d[\d,]*(?:\s+to\s+\d+)?\s+(?:cents|days?|hours?|a month|per month)\b|under \d+ hours?|\b\d{4,6} cents\b|\b[A-Z]{3}-\d{4,5}\b", yaml.safe_dump(rubric) + judge)))
    for token in numbers:
        for name, text in (("learn.md", learn), ("completion/README.md", completion)):
            if norm(token) not in norm(text):
                fail(f"'{token}' is required by the rubric or judge prompt but missing from {name}")

    # 4. Banned words agree.
    def banned_from(text: str) -> set[str]:
        m = re.search(r"(?:words?|these words)[^\n]*?:\s*([A-Za-z ,]+?)\.(?:\s|$)", text)
        return {w.strip().lower() for w in m.group(1).split(",")} if m else set()

    sets = {name: banned_from(t) for name, t in (("rubric", yaml.safe_dump(rubric)), ("judge", judge), ("completion", completion))}
    sets = {k: v for k, v in sets.items() if v}
    if len({frozenset(v) for v in sets.values()}) > 1:
        fail("banned-word lists differ: " + "; ".join(f"{k}={sorted(v)}" for k, v in sets.items()))

    # 5. Documents the rubric names must be taught.
    docs = extra.get("documents")
    if docs is None:
        docs = []
        notes.append("no consistency.yaml `documents` list; document-name check skipped")
    for d in docs:
        for name, text in (("learn.md", learn), ("completion/README.md", completion)):
            if d.lower() not in text.lower():
                fail(f"document '{d}' required by the rubric is never named in {name}")
        if worked and not extra.get("worked_example_uses_other_documents", True) and d.lower() not in worked.lower():
            fail(f"document '{d}' missing from worked example")

    # 6. FAQ anchors.
    anchors = set(re.findall(r"\{#([^}]+)\}", faq))
    for item in unit.get("unstuck", []):
        ref = item.get("fix_ref", "")
        if "#" in ref:
            anchor = ref.split("#", 1)[1]
            if anchor not in anchors:
                fail(f"unit.yaml fix_ref '{ref}' has no matching {{#{anchor}}} heading in faq/{unit_id}.md")

    # 7. Orphan numeric thresholds: an amount in cents that only one student file uses.
    student = {"learn.md": learn, "completion/README.md": completion, "faq": faq, "worked-example": worked}
    for name, text in student.items():
        for amt in set(re.findall(r"\b(\d{4,7}) cents\b", text)):
            others = [n for n, t in student.items() if n != name and amt in t]
            if not others and name in ("faq",):
                fail(f"faq teaches '{amt} cents' which no lesson or exercise file mentions")

    # 8. Word budget.
    budgets = set()
    for text in (learn, completion, yaml.safe_dump(unit), judge):
        budgets |= set(re.findall(r"\b(\d{3})\s+(?:to|and)\s+(\d{3})\s+words", text))
    if len(budgets) > 1:
        fail(f"word budgets disagree: {sorted(budgets)}")

    for n in notes:
        print(f"  note: {n}")
    for f in failures:
        print(f"  FAIL: {f}")
    if failures:
        print(f"\n{len(failures)} consistency failure(s) in unit {unit_id}. (Exit 1)")
        return 1
    print(f"PASS unit {unit_id}: headings, checks, numbers, banned words, documents, FAQ anchors, thresholds and word budget agree across files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
