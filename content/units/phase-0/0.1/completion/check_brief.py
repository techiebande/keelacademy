#!/usr/bin/env python3
"""Deterministic Layer-1 checks for Unit 0.1 Client Brief deliverables.

Validates client brief deliverables against the five rubric criteria and style constraints:
1. Heading structure (five exact headings in order).
2. No angle-bracket placeholders.
3. Word budget (250 to 500 words).
4. Zero banned technology words.
5. Copy bans (no em dashes, no en dashes, no exclamation marks, no buzzwords).
6. Problem section (<= 3 sentences, volume and wait duration measured).
7. Stakeholders section (3 distinct leaders with distinct outcomes).
8. Current process section (4 to 7 numbered steps, all documents named).
9. Target process section (4 to 7 numbered steps, under 1 hour, human reviewer, integer cents).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TECH_WORDS = [
    "ai", "agent", "agents", "llm", "llms", "model", "models", "prompt", "prompts",
    "automation", "automate", "automated", "software", "algorithm", "algorithms",
    "python", "docker", "api", "apis", "database", "databases", "json", "schema",
    "pipeline", "embedding", "embeddings", "token", "tokens", "chatbot", "machine learning",
]

BUZZWORDS = [
    "leverage", "synergy", "streamline", "unlock", "empower", "robust", "seamless",
    "cutting-edge", "revolutionise", "supercharge", "it is worth noting that",
]


def check_brief(path: Path) -> tuple[bool, list[str], list[str]]:
    """Evaluate a markdown file against all Unit 0.1 criteria.

    Returns:
        (passed, list_of_passes, list_of_failures)
    """
    if not path.is_file():
        return False, [], [f"file_exists: file not found at {path}"]

    text = path.read_text(encoding="utf-8")
    passes: list[str] = []
    failures: list[str] = []

    # 1. Heading structure
    headings = [l.strip() for l in text.splitlines() if re.match(r"^#{1,3}\s+", l.strip())]
    if len(headings) < 5:
        failures.append(f"heading_structure: expected at least 5 headings, found {len(headings)}")
    else:
        norm_h = [re.sub(r"^#{1,3}\s+", "", h).strip().lower() for h in headings[:5]]
        title = norm_h[0]
        if not ("client brief" in title and ("omnicart" in title or "apex freight" in title)):
            failures.append(f"heading_structure: title heading '{headings[0]}' must be 'OmniCart Operations: Client Brief' or 'Apex Freight Logistics: Client Brief'")
        else:
            passes.append(f"heading_structure: valid title heading '{headings[0]}'")

        expected_sections = ["the problem", "who cares and why", "how it works today", "how it should work"]
        if norm_h[1:5] == expected_sections:
            passes.append("heading_structure: four required section headings in exact order")
        else:
            failures.append(f"heading_structure: sections {norm_h[1:5]} do not match required {expected_sections}")

    is_omnicart = "omnicart" in text.lower()
    is_apex = "apex freight" in text.lower()

    # 2. Placeholders check
    placeholders = re.findall(r"<[^>]+>", text)
    if placeholders:
        failures.append(f"no_placeholders: found unreplaced placeholders: {placeholders}")
    else:
        passes.append("no_placeholders: zero unreplaced placeholders found")

    # 3. Word count check (250 to 500 words)
    words = re.findall(r"\b[\w'-]+\b", text)
    word_count = len(words)
    if 250 <= word_count <= 500:
        passes.append(f"word_budget: {word_count} words (within allowed 250 to 500 words)")
    else:
        failures.append(f"word_budget: {word_count} words (outside allowed 250 to 500 words)")

    # 4. Banned technology words
    tech_hits = []
    for w in TECH_WORDS:
        m = re.findall(rf"\b{re.escape(w)}\b", text, re.I)
        if m:
            tech_hits.extend(m)
    if tech_hits:
        failures.append(f"no_technology_words: found banned technology words: {tech_hits}")
    else:
        passes.append("no_technology_words: zero banned technology words found")

    # 5. Copy bans
    copy_errors = []
    if "\u2014" in text:
        copy_errors.append("em dash (U+2014)")
    if "\u2013" in text:
        copy_errors.append("en dash (U+2013)")
    if "!" in text:
        copy_errors.append("exclamation mark")
    for b in BUZZWORDS:
        if b in text.lower():
            copy_errors.append(f"buzzword '{b}'")
    if copy_errors:
        failures.append(f"copy_bans: violations found: {copy_errors}")
    else:
        passes.append("copy_bans: clean of dashes, exclamation marks, and corporate buzzwords")

    # Parse sections
    section_map: dict[str, str] = {}
    current_key = None
    current_lines = []
    for line in text.splitlines():
        if re.match(r"^#{1,3}\s+", line.strip()):
            if current_key is not None:
                section_map[current_key] = "\n".join(current_lines).strip()
            heading_title = re.sub(r"^#{1,3}\s+", "", line.strip()).strip().lower()
            current_key = heading_title
            current_lines = []
        else:
            current_lines.append(line)
    if current_key is not None:
        section_map[current_key] = "\n".join(current_lines).strip()

    # 6. Problem section
    prob_text = section_map.get("the problem", "")
    prob_sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", prob_text.replace("\n", " ")) if s.strip()]
    if not prob_text:
        failures.append("problem_section: 'The problem' section is empty")
    elif len(prob_sentences) > 3:
        failures.append(f"problem_section: {len(prob_sentences)} sentences (maximum 3 allowed)")
    else:
        prob_has_vol = bool(re.search(r"\b(?:about\s+)?(?:4,000|4000|3,500|3500)\b", prob_text, re.I))
        prob_has_wait = bool(re.search(r"\b2\s*(?:to|-)\s*3\s+days\b|\b2\s+days\b", prob_text, re.I))
        if prob_has_vol and prob_has_wait:
            passes.append(f"problem_section: {len(prob_sentences)} sentence(s) with volume and wait measured")
        else:
            missing = []
            if not prob_has_vol: missing.append("volume")
            if not prob_has_wait: missing.append("wait duration")
            failures.append(f"problem_section: missing {missing}")

    # 7. Stakeholders section
    who_text = section_map.get("who cares and why", "")
    if not who_text:
        failures.append("stakeholders_section: 'Who cares and why' section is empty")
    else:
        if is_omnicart:
            has_ops = bool(re.search(r"\b(vp of operations|sarah jenkins)\b", who_text, re.I))
            has_cfo = bool(re.search(r"\b(cfo|chief financial officer|finance chief)\b", who_text, re.I))
            has_trust = bool(re.search(r"\b(?:trust\s+(?:and|&)\s+safety\s+officer|policy\s+officer)\b", who_text, re.I))
            if has_ops and has_cfo and has_trust:
                passes.append("stakeholders_section: VP of Operations, CFO, and Trust and Safety Officer named")
            else:
                missing = []
                if not has_ops: missing.append("VP of Operations")
                if not has_cfo: missing.append("CFO")
                if not has_trust: missing.append("Trust and Safety Officer")
                failures.append(f"stakeholders_section: missing roles {missing}")
        elif is_apex:
            has_marcus = bool(re.search(r"\bmarcus bell\b", who_text, re.I))
            has_priya = bool(re.search(r"\bpriya nair\b", who_text, re.I))
            has_dana = bool(re.search(r"\bdana okafor\b", who_text, re.I))
            if has_marcus and has_priya and has_dana:
                passes.append("stakeholders_section: Marcus Bell, Priya Nair, and Dana Okafor named")
            else:
                missing = []
                if not has_marcus: missing.append("Marcus Bell")
                if not has_priya: missing.append("Priya Nair")
                if not has_dana: missing.append("Dana Okafor")
                failures.append(f"stakeholders_section: missing stakeholders {missing}")
        else:
            failures.append("stakeholders_section: unknown client entity")

    # 8. Current process section
    cur_text = section_map.get("how it works today", "")
    cur_steps = re.findall(r"^\d+\.\s+(.*)$", cur_text, re.M)
    if not cur_text:
        failures.append("current_process_section: 'How it works today' section is empty")
    elif not (4 <= len(cur_steps) <= 7):
        failures.append(f"current_process_section: found {len(cur_steps)} numbered steps (must be 4 to 7)")
    else:
        if is_omnicart:
            req_docs = ["order receipt", "delivery slip", "unboxing photo", "return policy"]
            missing_docs = [d for d in req_docs if d not in cur_text.lower()]
            if missing_docs:
                failures.append(f"current_process_section: missing required document(s): {missing_docs}")
            else:
                passes.append(f"current_process_section: {len(cur_steps)} numbered steps naming all four required documents")
        elif is_apex:
            req_docs = ["rate confirmation", "bill of lading", "detention log", "damage claim", "carrier invoice"]
            missing_docs = [d for d in req_docs if d not in cur_text.lower()]
            if missing_docs:
                failures.append(f"current_process_section: missing carrier document(s): {missing_docs}")
            else:
                passes.append(f"current_process_section: {len(cur_steps)} numbered steps naming carrier audit documents")
        else:
            passes.append(f"current_process_section: {len(cur_steps)} numbered steps present")

    # 9. Target process section
    tgt_text = section_map.get("how it should work", "")
    tgt_steps = re.findall(r"^\d+\.\s+(.*)$", tgt_text, re.M)
    if not tgt_text:
        failures.append("target_process_section: 'How it should work' section is empty")
    elif not (4 <= len(tgt_steps) <= 7):
        failures.append(f"target_process_section: found {len(tgt_steps)} numbered steps (must be 4 to 7)")
    else:
        has_target_time = bool(re.search(r"\b(?:under|within)\s+(?:1\s+hour|one\s+hour|60\s+minutes)\b", tgt_text, re.I))
        has_human = bool(re.search(r"\b(human|person|reviewer|clerk|specialist|manager)\b", tgt_text, re.I))
        has_cents = bool(re.search(r"\b\d+\s*cents\b", tgt_text, re.I))
        if has_target_time and has_human and has_cents:
            passes.append(f"target_process_section: {len(tgt_steps)} numbered steps with under 1 hour target, human reviewer, and integer cents")
        else:
            missing = []
            if not has_target_time: missing.append("under 1 hour target")
            if not has_human: missing.append("human reviewer for hard cases")
            if not has_cents: missing.append("integer cents amount")
            failures.append(f"target_process_section: missing {missing}")

    success = len(failures) == 0
    return success, passes, failures


def run_single(file_path: Path) -> int:
    print(f"Checking client brief: {file_path}")
    passed, passes, failures = check_brief(file_path)
    for p in passes:
        print(f"  PASS [{p}]")
    for f in failures:
        print(f"  FAIL [{f}]")
    if passed:
        print(f"\nOVERALL: PASS ({len(passes)} checks passed, 0 failures)")
        return 0
    print(f"\nOVERALL: FAIL ({len(failures)} check(s) failed)")
    return 1


def run_self_test() -> int:
    repo_root = Path(__file__).resolve().parents[5]
    playtester_draft = repo_root / "scratch/playtester-draft.md"
    targets = [
        (repo_root / "apex-freight/docs/client-brief.md", True, "Apex Freight model deliverable"),
        (repo_root / "omnicart-system/docs/client-brief.md", True, "OmniCart reference solution"),
    ]
    if playtester_draft.is_file():
        targets.append((playtester_draft, True, "Blind playtester draft deliverable"))
    targets.append((repo_root / "content/units/phase-0/0.1/completion/template.md", False, "Base incomplete template"))

    print("================================================================")
    print("Unit 0.1 Client Brief Verification Suite")
    print("================================================================")

    all_matched = True
    for path, expected_pass, label in targets:
        print(f"\n--- Testing {label} ({path.relative_to(repo_root) if path.is_relative_to(repo_root) else path}) ---")
        passed, passes, failures = check_brief(path)
        for p in passes:
            print(f"  PASS [{p}]")
        for f in failures:
            print(f"  FAIL [{f}]")

        matches = (passed == expected_pass)
        if matches:
            outcome = "PASS (as expected)" if expected_pass else "FAIL (as expected)"
            print(f"Result: {outcome}")
        else:
            outcome = "UNEXPECTED PASS" if passed else "UNEXPECTED FAIL"
            print(f"Result: {outcome}")
            all_matched = False

    print("\n================================================================")
    if all_matched:
        print("ALL VERIFICATION CHECKS PASSED: Model & reference passed, template failed as expected.")
        return 0
    print("VERIFICATION CHECKS FAILED: At least one outcome drifted from expectation.")
    return 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] not in ("--self-test", "-t"):
        return run_single(Path(sys.argv[1]))
    return run_self_test()


if __name__ == "__main__":
    sys.exit(main())
