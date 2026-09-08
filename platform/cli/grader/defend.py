"""Layer-3 defend-your-work CLI.

Usage:
    python -m grader.defend <submission_dir> [--tier mid] [--json out.json]

Reads the submission as text (never executes it) and asks the LLM for exactly
2–3 follow-up questions that only the person who actually wrote the code can
answer — each targeting a concrete function, variable, constant, or branch from
THIS submission. The CLI never trusts the model: every question must carry
non-empty `anchors` (identifiers, paths, or code fragments) that literally
appear in the submission's text; a missing anchor triggers one retry with a
nudge, then a hard error (exit 2). Output is validated against
defend.schema.json.

API key: OPENAI_API_KEY from the environment only. LLM plumbing in grader/llm.py;
submission reading in grader/submission.py (grade.yaml never reaches the model).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from .llm import (MODEL_TIERS, LLMError, begin_trace_call, call_with_json_retry, require_api_key,
                  set_trace_caller, set_trace_tier, trace)
from .submission import SubmissionError, gather_submission

SCHEMA_PATH = Path(__file__).with_name("defend.schema.json")

ANCHOR_NUDGE = (
    "Some of your anchors do not appear verbatim in the submission's code. "
    "Regenerate the full JSON with the same shape, but every anchor must be a "
    "string copied EXACTLY (character for character) from the submission's "
    "files — an identifier, a file path, or a short code fragment that exists "
    "in the code. Do not paraphrase or abbreviate anchors."
)


def build_prompt(submission_text: str) -> str:
    return f"""You are generating a "defend your work" interview for a student who
  submitted the code below. Produce 2–3 follow-up questions (3 if there are
  three strong targets; 2 if not) that ONLY the person who actually wrote this
  code could answer well — someone who copy-pasted it or had an AI write it
  should struggle.

Rules for every question:
- It must target concrete code from THIS submission: a specific function,
  variable, constant, default value, or branch. Name the identifier in the
  question.
- It must probe understanding, not recall: why this value, what happens on
  this input, why not the obvious alternative, what breaks if this line is
  removed or changed. Never "explain what X is" textbook questions.
- At least one question should target something a non-author could not
  explain: a magic constant, an edge-case branch, or a non-obvious design
  choice.
- STRONG targets: how the LLM is invoked (response_format settings,
  strictness flags, which fields are sent), truncation/limiting constants
  (e.g. slicing an error message), unusual field defaults, rare branches.
  WEAK targets (avoid unless nothing stronger exists): standard validation
  patterns, fallback defaults, or anything another solution to this problem
  would likely contain verbatim.
- Questions must be answerable in 2–3 sentences by the real author.

Return ONLY a JSON object (no markdown fences, no commentary) of the form:

{{
  "questions": [
    {{"id": "q1", "question": "...", "anchors": ["...", "..."]}},
    {{"id": "q2", "question": "...", "anchors": ["..."]}}
  ]
}}

Each `anchors` list has 1–3 entries: exact identifiers, file paths, or short
code fragments copied verbatim from the submission that the question targets.
Each id is unique: q1, q2, q3.

## Submission

```
{submission_text}
```
"""


class DefendError(Exception):
    pass


def check_anchors(questions: list[dict], submission_text: str) -> list[str]:
    """Return the list of anchors that do NOT literally appear in the submission."""
    missing = []
    for q in questions:
        for anchor in q.get("anchors", []):
            if anchor not in submission_text:
                missing.append(f"{q.get('id', '?')}: {anchor!r}")
    return missing


def defend(submission_dir: Path, tier: str) -> dict:
    set_trace_caller("defend")
    api_key = require_api_key()
    if tier not in MODEL_TIERS:
        raise DefendError(f"unknown tier {tier!r} (have {sorted(MODEL_TIERS)})")
    model = MODEL_TIERS[tier]["model"]
    set_trace_tier(tier)

    submission_text = gather_submission(submission_dir)
    prompt = build_prompt(submission_text)

    messages = [{"role": "user", "content": prompt}]
    parsed = meta = None
    for attempt in (1, 2):
        try:
            parsed, meta = call_with_json_retry(model, messages, api_key)
        except LLMError as exc:
            raise DefendError(str(exc)) from exc
        missing = check_anchors(parsed.get("questions", []), submission_text)
        if not missing:
            break
        if attempt == 2:
            raise DefendError("anchors missing from submission after retry: " + "; ".join(missing))
        # anchor nudge: re-ask with the failure named, keeping the conversation
        reply = json.dumps(parsed)
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": ANCHOR_NUDGE + "\n\nMissing anchors: "
                     + "; ".join(missing)},
        ]

    result = {
        "submission_ref": submission_dir.resolve().as_posix(),
        "tier": tier,
        "questions": [
            {"id": q["id"], "question": q["question"], "anchors": list(q["anchors"])}
            for q in parsed["questions"]
        ],
        "meta": meta,
    }

    errors = sorted(Draft202012Validator(json.loads(SCHEMA_PATH.read_text())).iter_errors(result),
                    key=lambda e: e.json_path)
    if errors:
        raise DefendError("output failed schema validation: " + "; ".join(
            f"{e.json_path}: {e.message}" for e in errors))

    return result


def human_summary(result: dict) -> None:
    for q in result["questions"]:
        print(f"\n[{q['id']}] {q['question']}")
        print(f"     anchors: {', '.join(q['anchors'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="grader.defend",
                                 description="keelacademy Layer-3 defend-your-work question generator")
    ap.add_argument("submission_dir", type=Path)
    ap.add_argument("--tier", choices=sorted(MODEL_TIERS), default="mid",
                    help="model tier (default: mid)")
    ap.add_argument("--json", type=Path, help="write the question JSON here")
    args = ap.parse_args(argv)

    if not args.submission_dir.is_dir():
        print(f"error: submission dir not found: {args.submission_dir}", file=sys.stderr)
        return 2
    begin_trace_call()
    try:
        result = defend(args.submission_dir, args.tier)
    except (DefendError, SubmissionError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    trace(result["meta"])
    human_summary(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2))
        print(f"\nquestion JSON written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
