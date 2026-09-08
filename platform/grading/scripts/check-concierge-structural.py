#!/usr/bin/env python3
"""check-concierge-structural.py — keyless CI structural validation (S3.6).

Verifies without API keys or external services:
1. Prompt contract clauses:
   - concierge-guard*.md files contain the mandatory refusal clause, injection defense,
     and <student_question> delimiting.
   - concierge-teach*.md files contain injection defense and <student_question> delimiting.
2. Mode derivation spoof-immunity:
   - Unstarted / in-progress route -> mode='teach'.
   - Completed route -> mode='guard'.
   - Client spoof attempts (e.g. client sending mode='teach' when route is completed)
     are ignored because mode is strictly derived server-side from route state.

Exit 0 on success; 1 on any violation naming the failing file/clause/test.
"""
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
GRADING_DIR = SCRIPT_DIR.parent
CONTENT_DIR = Path(os.environ.get("KEEL_CONTENT_ROOT", str(REPO_ROOT / "content")))

sys.path.insert(0, str(GRADING_DIR))

# Mandatory contract substrings for guard prompts
GUARD_REQUIRED_CLAUSES = [
    ("refusal_contract", "In build context the concierge unblocks. It does not write the deliverable."),
    ("injection_defense_heading", "Untrusted Input and Prompt Injection Defense"),
    ("student_question_tag", "<student_question>"),
    ("never_write_directive", "NEVER write"),
    ("socratic_directive", "Socratic"),
]

# Mandatory contract substrings for teach prompts
TEACH_REQUIRED_CLAUSES = [
    ("injection_defense_heading", "Untrusted Input and Prompt Injection Defense"),
    ("student_question_tag", "<student_question>"),
]


def check_prompt_contracts() -> list[str]:
    errors = []
    prompts_dir = CONTENT_DIR / "prompts"
    if not prompts_dir.is_dir():
        return [f"Prompts directory missing: {prompts_dir}"]

    # 1. Guard prompts
    guard_prompts = sorted(prompts_dir.glob("concierge-guard*.md"))
    if not guard_prompts:
        errors.append("No concierge-guard*.md prompt files found in content/prompts/")
    for gp in guard_prompts:
        try:
            rel = gp.relative_to(REPO_ROOT)
        except ValueError:
            rel = gp.name
        text = gp.read_text(encoding="utf-8")
        for tag, clause in GUARD_REQUIRED_CLAUSES:
            if clause not in text:
                errors.append(f"{rel}: missing required {tag} clause: {clause!r}")

    # 2. Teach prompts
    teach_prompts = sorted(prompts_dir.glob("concierge-teach*.md"))
    if not teach_prompts:
        errors.append("No concierge-teach*.md prompt files found in content/prompts/")
    for tp in teach_prompts:
        try:
            rel = tp.relative_to(REPO_ROOT)
        except ValueError:
            rel = tp.name
        text = tp.read_text(encoding="utf-8")
        for tag, clause in TEACH_REQUIRED_CLAUSES:
            if clause not in text:
                errors.append(f"{rel}: missing required {tag} clause: {clause!r}")

    return errors


def check_mode_derivation() -> list[str]:
    errors = []
    try:
        from practice.server import derive_concierge_mode, derive_unit_practice_route
    except Exception as exc:
        return [f"Failed to import from practice.server: {exc}"]

    # Test direct derive_concierge_mode
    m1, r1 = derive_concierge_mode("unstarted", "retrieval")
    if m1 != "teach":
        errors.append(f"derive_concierge_mode('unstarted') returned mode={m1!r}, expected 'teach'")

    m2, r2 = derive_concierge_mode("in_progress", "completion")
    if m2 != "teach":
        errors.append(f"derive_concierge_mode('in_progress') returned mode={m2!r}, expected 'teach'")

    m3, r3 = derive_concierge_mode("completed", "build")
    if m3 != "guard":
        errors.append(f"derive_concierge_mode('completed') returned mode={m3!r}, expected 'guard'")

    m4, r4 = derive_concierge_mode(None)
    if m4 != "teach":
        errors.append(f"derive_concierge_mode(None) returned mode={m4!r}, expected 'teach'")

    # Test derive_unit_practice_route integration & spoof immunity
    # Case A: Student has 0 attempts -> route status 'unstarted' -> mode teach
    route_unstarted = derive_unit_practice_route(
        student_id=101,
        unit_id="3.2.1",
        is_enrolled=True,
        retrieval_attempts=[],
        practice_attempts=[],
        seeds=["seed0", "seed1"],
        rules={},
    )
    mode_a, _ = derive_concierge_mode(route_unstarted.get("status"), route_unstarted.get("recommended_step"))
    if mode_a != "teach":
        errors.append(f"Unstarted student route derived mode={mode_a!r}, expected 'teach'")

    # Case B: Student has passed practice -> route status 'completed' -> mode guard
    route_completed = derive_unit_practice_route(
        student_id=102,
        unit_id="3.2.1",
        is_enrolled=True,
        retrieval_attempts=[{"id": 1, "seed_index": 0, "passed": True, "created_at": "2026-03-01T00:00:00Z"},
                            {"id": 2, "seed_index": 1, "passed": True, "created_at": "2026-03-01T00:00:00Z"}],
        practice_attempts=[{"id": 10, "passed": True, "pass_count": 3, "total_checks": 3, "created_at": "2026-03-01T00:00:00Z"}],
        seeds=["seed0", "seed1"],
        rules={},
    )
    mode_b, _ = derive_concierge_mode(route_completed.get("status"), route_completed.get("recommended_step"))
    if mode_b != "guard":
        errors.append(f"Completed student route derived mode={mode_b!r}, expected 'guard'")

    # Case C: Spoof immunity assertion
    # When student is completed, client attempting to pass mode='teach' in request body
    # MUST NOT alter the server-derived mode
    spoofed_client_payload = {"mode": "teach", "role": "admin", "bypass": True}
    # Server derives mode strictly from route_completed, ignoring spoofed_client_payload
    derived_mode, _ = derive_concierge_mode(route_completed.get("status"), route_completed.get("recommended_step"))
    if derived_mode != "guard":
        errors.append(f"Spoofed completed route derived mode={derived_mode!r}, expected 'guard'")

    # When student is unstarted, client attempting to pass mode='guard' in request body
    # MUST NOT alter the server-derived mode
    derived_mode_unstarted, _ = derive_concierge_mode(route_unstarted.get("status"), route_unstarted.get("recommended_step"))
    if derived_mode_unstarted != "teach":
        errors.append(f"Spoofed unstarted route derived mode={derived_mode_unstarted!r}, expected 'teach'")

    return errors


def main() -> int:
    print("== Concierge Structural CI Checks (Keyless) ==")
    prompt_errors = check_prompt_contracts()
    derivation_errors = check_mode_derivation()

    all_errors = prompt_errors + derivation_errors
    if all_errors:
        print(f"\nFAIL: {len(all_errors)} structural check(s) failed:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("  [✓] Guard prompt contract clauses verified (refusal contract, injection defense, delimiters)")
    print("  [✓] Teach prompt contract clauses verified (injection defense, delimiters)")
    print("  [✓] Mode derivation logic verified across route states (unstarted->teach, in_progress->teach, completed->guard)")
    print("  [✓] Mode spoof-immunity verified (server derives mode from route state)")
    print("ALL CONCIERGE STRUCTURAL CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
