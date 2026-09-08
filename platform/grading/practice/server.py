#!/usr/bin/env python3
"""practice/server.py — completion problem & retrieval drill practice grading service (S3.1, S3.2, S3.3).

Exposes:
1. Fast, deterministic, sandboxed Layer-1 grading for completion problems (S3.1)
   without LLM judge calls or budget consumption.
2. Layer-2 judge grading for free-recall retrieval drills (S3.2) routed through
   the LLM proxy with per-student budgets, trace logging, and prompt-injection defense.
3. Spaced re-check scheduling (S3.3): passed retrieval seeds come back as due
   re-checks at +3 days, then +7 days, then retire. The schedule is DERIVED at
   read time from retrieval_attempts (no new table, no daemon). Deterministic
   clock knobs KEEL_PRACTICE_NOW / KEEL_PRACTICE_NOW_FILE exist for proofs;
   production leaves both unset.
4. Drill token economics (S3.3): the judge prompt carries a deterministic
   excerpt of the lesson (stdlib-only heading/keyword section scoring under a
   char budget, KEEL_RETRIEVAL_EXCERPT_CHARS; <=0 restores the full lesson)
   instead of the full lesson text. The excerpt header (chars sent, sections
   chosen) is embedded in the prompt itself, so every trace record is
   cost-auditable.

The learner app calls this service from server components / actions using the shared
app token (KEEL_ENROLL_SECRET).

Routes:
    GET  /healthz                                         -> {"ok": true}
    GET  /practice/manifest?unit=<id>                     -> completion manifest
    POST /practice/attempt                                -> stage base + student files -> sandbox grade -> persist
    GET  /practice/attempts?student_id=<id>&unit=<id>     -> student completion attempt history
    GET  /practice/retrieval/seeds?unit=<id>              -> authored retrieval seeds (v1 deterministic)
    POST /practice/retrieval/attempt                      -> grade retrieval answer via LLM proxy judge -> persist
    GET  /practice/retrieval/attempts?student_id=<id>&unit=<id> -> student retrieval attempt history
    GET  /practice/retrieval/schedule?student_id=<id>[&unit=<id>] -> derived spaced re-check schedule (S3.3)
    GET  /practice/route?student_id=<id>&unit=<id>        -> derived adaptive practice route (S3.4)
    POST /concierge/ask                                   -> derive mode -> call proxy -> persist -> return {mode, mode_reason, answer, tokens_charged} (S3.5)
    GET  /concierge/turns?student_id=<id>&unit=<id>       -> student concierge turn history (S3.5)
    GET  /diagnostic/spec?id=<id>                         -> diagnostic question set and placement threshold (S4.1)
    POST /diagnostic/evaluate                             -> evaluate answers, compute placement route, unlock units -> persist -> return {score_pct, passed, route, breakdown} (S4.1)
    GET  /diagnostic/attempts?student_id=<id>             -> student diagnostic attempt history (S4.1)
    POST /diagnostic/opt-out                              -> student opts out -> route to baseline 0.1/1.1 (S4.1)
    POST /gallery/publish                                 -> publish/showcase passed verified project (S4.4)
    POST /gallery/unpublish                               -> unpublish/hide project from gallery (S4.4)
    GET  /gallery                                         -> public gallery listing with phase/unit filter (S4.4)
    GET  /gallery/<id>                                    -> project detail with verified rubric proof (S4.4)

Security & Boundaries:
    - Auth: X-Keel-App-Token header matched to env KEEL_ENROLL_SECRET.
    - Enrollment Gate: Only students with an ACTIVE enrollment for the unit may attempt / ask.
    - Whitelisting (completion): Only files in the unit's editable_files whitelist are accepted.
    - Budget Gate (retrieval & concierge): Grader routes through the platform proxy; 429 budget_exceeded
      declines the request BEFORE any model call and writes zero attempt/turn rows.
    - Untrusted code execution: Sandbox only (Docker via platform/grading/layer1.py).
    - Untrusted answers & questions: Quoted as data, anti-injection prompt defense applied.
    - DB Access: Env KEEL_DB_CMD via shared db.py; attempt/turn rows + spine events
      (practice.attempt_graded, practice.retrieval_graded, concierge.answered) commit in atomic transactions.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

# Add grading dir to sys.path to import shared modules (db, layer1)
GRADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GRADING_DIR))
from db import db_sql, sql_str
import layer1
import community.pods as pods
import community.digests as digests
import community.gallery as gallery
import simulation.engine as simulation
import analytics.engine as analytics

MAX_BODY_BYTES = 1 * 1024 * 1024       # 1 MB total request body cap
MAX_FILE_BYTES = 128 * 1024             # 128 KB per individual file/answer cap
MAX_FILENAME_LEN = 128
UNIT_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULT_TIMEOUT_S = 60

MODEL_PRICES = {
    "gpt-4o-mini": {"price_in": 0.15, "price_out": 0.60},
    "gpt-4.1": {"price_in": 2.00, "price_out": 8.00},
    "o3": {"price_in": 2.00, "price_out": 8.00},
}

NUDGE_MSG = (
    "Your previous reply was not valid JSON. Return ONLY a single JSON object "
    "conforming to the schema from the original prompt — no markdown fences, "
    "no commentary before or after."
)


class BudgetExceeded(Exception):
    """The proxy answered 429 budget_exceeded."""
    pass


class UpstreamError(Exception):
    """Network, connection, or upstream failure."""
    pass


class MalformedJudgeError(Exception):
    """Judge returned malformed JSON twice."""
    pass


class RubricError(Exception):
    """Unit rubric missing/unreadable — conceptual grading cannot proceed."""
    pass


RUBRIC_INSERT_RE = re.compile(r"<!--\s*RUBRIC_INSERT[^>]*-->", re.IGNORECASE)


def app_token() -> str:
    return os.environ.get("KEEL_ENROLL_SECRET", "")


def content_root() -> Path:
    return layer1.content_root()


def resolve_unit_ref(unit_yaml_path: Path, ref: str) -> Path | None:
    """Resolve a unit.yaml path reference the same way the app does.

    Unit-local first (the authoring convention), then content root; a leading
    "content/" prefix is tolerated. Returns None when nothing exists.
    """
    if not ref:
        return None
    rel = ref.removeprefix("content/")
    unit_dir = unit_yaml_path.parent
    root = content_root()
    for candidate in (unit_dir / rel, root / rel):
        if candidate.exists():
            return candidate
    return None


def get_unit_practice_manifest(unit_id: str) -> dict[str, Any] | None:
    """Read completion problem manifest from content repo for unit_id."""
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if not matches:
        return None
    unit_yaml_path = matches[0]
    try:
        unit_data = yaml.safe_load(unit_yaml_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    practice = unit_data.get("practice") or {}
    completion = practice.get("completion_problem")
    if not isinstance(completion, dict):
        return None

    kind = unit_data.get("kind", "code")
    if kind == "conceptual" or "prompt" in completion:
        prompt_text = completion.get("prompt", "")
        instructions = completion.get("instructions", "")
        we_rel = practice.get("worked_example", "")
        we_path = resolve_unit_ref(unit_yaml_path, we_rel) if we_rel else None
        # The ref may name the README itself or its directory.
        we_readme_path = None
        we_base_dir = None
        if we_path is not None:
            if we_path.is_dir():
                we_readme_path = we_path / "README.md"
                we_base_dir = we_path
            else:
                we_readme_path = we_path
                we_base_dir = we_path.parent
        model_answer_md = we_readme_path.read_text(encoding="utf-8") if we_readme_path and we_readme_path.is_file() else ""
        return {
            "unit_id": unit_id,
            "kind": "conceptual",
            "prompt": prompt_text,
            "instructions": instructions,
            "model_answer_markdown": model_answer_md,
            "base_rel": we_rel,
            "readme_markdown": model_answer_md,
            "base_files": {},
            "editable_files": [],
            "checks": [{"id": "conceptual-rubric-judge", "type": "llm-judge"}],
            "checks_path": None,
            "base_dir": we_base_dir,
        }

    base_rel = completion.get("base")
    checks_rel = completion.get("checks")
    if not base_rel or not checks_rel:
        return None

    base_dir = resolve_unit_ref(unit_yaml_path, base_rel)
    checks_path = resolve_unit_ref(unit_yaml_path, checks_rel)
    if base_dir is None or not base_dir.is_dir() or checks_path is None or not checks_path.is_file():
        return None

    readme_path = base_dir / "README.md"
    readme_md = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""

    # Read base files, skipping cache and hidden entries
    base_files: dict[str, str] = {}
    for entry in sorted(base_dir.iterdir()):
        if entry.is_file() and not entry.name.startswith("."):
            try:
                base_files[entry.name] = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

    # Determine editable files by looking for GAP markers in base files
    editable_files: list[str] = []
    for fname, content in base_files.items():
        if fname.endswith(".py") and re.search(r"#\s*GAP\s+\d+", content):
            editable_files.append(fname)
    if not editable_files:
        for fname in base_files:
            if fname.endswith(".py") and not fname.startswith("test_") and fname not in ("llm.py", "notes.py"):
                editable_files.append(fname)
    editable_files.sort()

    try:
        checks_data = yaml.safe_load(checks_path.read_text(encoding="utf-8"))
        if not isinstance(checks_data, list):
            checks_data = []
    except Exception:
        checks_data = []

    check_descriptors = [
        {"id": c.get("id"), "type": c.get("type")}
        for c in checks_data if isinstance(c, dict) and "id" in c
    ]

    return {
        "unit_id": unit_id,
        "kind": "code",
        "base_rel": base_rel.rstrip("/") + "/",
        "readme_markdown": readme_md,
        "base_files": base_files,
        "editable_files": editable_files,
        "checks": check_descriptors,
        "checks_path": checks_path,
        "base_dir": base_dir,
    }


def get_unit_retrieval_seeds(unit_id: str) -> list[str]:
    """Read authored retrieval seeds from unit.yaml in content repo."""
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if not matches:
        return []
    try:
        unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
        seeds = (unit_data.get("practice") or {}).get("retrieval_seeds") or []
        if isinstance(seeds, list):
            return [str(s) for s in seeds if s]
        return []
    except Exception:
        return []


def get_unit_learn_text(unit_id: str) -> str:
    """Read lesson markdown for unit_id from content repo.

    A lesson authored as a unit script carries ':::' marker lines telling the
    page where to place its own apparatus (the workbench, the checks table, the
    rubric). Those lines are page structure, not teaching, so they are dropped
    here, at the single point all three lesson-reading paths go through:
    retrieval grading, recheck and the concierge. The excerpt a judge sees is
    strictly cleaner for it, and a marker can never be mistaken for content the
    student was supposed to have read.
    """
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if not matches:
        raise RuntimeError(f"unit {unit_id} not found in content repository")
    try:
        unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to parse unit.yaml for {unit_id}: {exc}") from exc
    learn_rel = unit_data.get("learn")
    if not learn_rel:
        raise RuntimeError(f"learn path not declared for unit {unit_id}")
    # unit-local first (the unit.yaml convention), then content root; a leading
    # "content/" prefix is tolerated either way.
    unit_dir = matches[0].parent
    rel = learn_rel.removeprefix("content/")
    learn_path = next(
        (c for c in (unit_dir / rel, root / rel) if c.is_file()),
        None,
    )
    if learn_path is None:
        raise RuntimeError(f"learn file not found: {learn_rel}")
    return strip_script_markers(learn_path.read_text(encoding="utf-8"))


def get_retrieval_prompt_text(unit_id: str) -> str:
    """Read retrieval judge prompt template from content/prompts/."""
    root = content_root()
    prompts_dir = root / "prompts"
    unit_prompt = prompts_dir / f"retrieval-{unit_id}.md"
    general_prompt = prompts_dir / "retrieval-grade.md"
    if unit_prompt.is_file():
        return unit_prompt.read_text(encoding="utf-8")
    if general_prompt.is_file():
        return general_prompt.read_text(encoding="utf-8")
    raise RuntimeError(f"retrieval judge prompt not found in {prompts_dir}")


def get_concierge_teach_prompt(unit_id: str) -> str:
    """Read concierge teach prompt template from content/prompts/ (S3.5)."""
    root = content_root()
    prompts_dir = root / "prompts"
    unit_prompt = prompts_dir / f"concierge-teach-{unit_id}.md"
    general_prompt = prompts_dir / "concierge-teach.md"
    if unit_prompt.is_file():
        return unit_prompt.read_text(encoding="utf-8")
    if general_prompt.is_file():
        return general_prompt.read_text(encoding="utf-8")
    raise RuntimeError(f"concierge teach prompt not found in {prompts_dir}")


def get_concierge_guard_prompt(unit_id: str) -> str:
    """Read concierge guard prompt template from content/prompts/ (S3.5)."""
    root = content_root()
    prompts_dir = root / "prompts"
    unit_prompt = prompts_dir / f"concierge-guard-{unit_id}.md"
    general_prompt = prompts_dir / "concierge-guard.md"
    if unit_prompt.is_file():
        return unit_prompt.read_text(encoding="utf-8")
    if general_prompt.is_file():
        return general_prompt.read_text(encoding="utf-8")
    raise RuntimeError(f"concierge guard prompt not found in {prompts_dir}")


def get_diagnostic_spec(diagnostic_id: str = "placement-phase-1") -> dict[str, Any] | None:
    """Read placement diagnostic specification from content/diagnostic/*.yaml (S4.1)."""
    root = content_root()
    diag_dir = root / "diagnostic"
    target = diag_dir / f"{diagnostic_id}.yaml"
    if not target.is_file():
        # Fall back to any yaml matching diagnostic_id
        matches = sorted(diag_dir.glob("*.yaml")) if diag_dir.is_dir() else []
        for m in matches:
            try:
                doc = yaml.safe_load(m.read_text(encoding="utf-8"))
                if isinstance(doc, dict) and doc.get("id") == diagnostic_id:
                    return doc
            except Exception:
                continue
        if matches:
            try:
                return yaml.safe_load(matches[0].read_text(encoding="utf-8"))
            except Exception:
                return None
        return None
    try:
        return yaml.safe_load(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def evaluate_diagnostic(spec: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    """Score diagnostic answers deterministically against the rubric spec (S4.1).
    
    Returns breakdown, points_earned, points_possible, score_pct, passed, route, unlocks.
    """
    questions = spec.get("questions") or []
    threshold_pct = float(spec.get("passing_threshold_pct", 75.0))
    pass_units = spec.get("pass_skip_units") or ["1.3", "1.4", "1.5"]
    fail_units = spec.get("fail_baseline_units") or ["0.1", "1.1", "1.2"]

    total_points = 0
    earned_points = 0
    breakdown = []

    for q in questions:
        qid = q.get("id")
        pts = int(q.get("points", 1))
        correct_opt = str(q.get("correct_answer", "")).strip()
        student_ans = str(answers.get(qid, "")).strip()
        is_correct = (student_ans == correct_opt) and bool(student_ans)

        total_points += pts
        if is_correct:
            earned_points += pts

        breakdown.append({
            "question_id": qid,
            "category": q.get("category"),
            "points_possible": pts,
            "points_earned": pts if is_correct else 0,
            "correct": is_correct,
            "submitted_answer": student_ans,
            "correct_answer": correct_opt,
            "explanation": q.get("explanation", ""),
        })

    if total_points > 0:
        score_pct = round((earned_points / total_points) * 100.0, 2)
    else:
        score_pct = 0.0

    passed = score_pct >= threshold_pct
    route = "1.3_skip" if passed else "baseline_0.1"
    unlocked_units = pass_units if passed else fail_units

    return {
        "diagnostic_id": spec.get("id"),
        "points_earned": earned_points,
        "points_possible": total_points,
        "score_pct": score_pct,
        "passing_threshold_pct": threshold_pct,
        "passed": passed,
        "route": route,
        "unlocked_units": unlocked_units,
        "breakdown": breakdown,
    }


def get_unit_faq_text(unit_id: str) -> str:
    """Read unit FAQ markdown from content repo if available."""
    root = content_root()
    faq_path = root / "faq" / f"{unit_id}.md"
    if faq_path.is_file():
        try:
            return faq_path.read_text(encoding="utf-8")
        except Exception:
            return ""
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if matches:
        try:
            unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
            unstuck = unit_data.get("unstuck") or []
            if unstuck:
                lines = ["## Unstuck Guidelines\n"]
                for item in unstuck:
                    symptom = item.get("symptom", "")
                    fix_ref = item.get("fix_ref", "")
                    lines.append(f"- Symptom: {symptom} (Ref: {fix_ref})")
                return "\n".join(lines)
        except Exception:
            pass
    return ""


def get_unit_guard_context(unit_id: str) -> tuple[str, str]:
    """Read deliverable text and rubric criteria summary for unit_id."""
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if not matches:
        raise RuntimeError(f"unit {unit_id} not found in content repository")
    try:
        unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to parse unit.yaml for {unit_id}: {exc}") from exc

    deliverable = (unit_data.get("build") or {}).get("deliverable", "")
    if not deliverable:
        deliverable = f"Deliverable for unit {unit_id}"

    # Load rubric criteria summary
    rubric_rel = (unit_data.get("verify") or {}).get("rubric")
    criteria_lines = []
    if rubric_rel:
        rubric_path = root / rubric_rel
        if rubric_path.is_file():
            try:
                rdata = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
                for crit in rdata.get("criteria", []):
                    cid = crit.get("id", "")
                    desc = crit.get("description", "")
                    criteria_lines.append(f"- {cid}: {desc}")
            except Exception:
                pass
    rubric_summary = "\n".join(criteria_lines) if criteria_lines else "Standard unit rubric criteria apply."
    return deliverable, rubric_summary


# --------------------------------------------------------------------------
# S3.3 — deterministic clock (spaced re-check proofs)
# --------------------------------------------------------------------------

def practice_now() -> datetime:
    """Current instant for the re-check scheduler.

    KEEL_PRACTICE_NOW (ISO 8601) fixes 'now' for the whole process;
    KEEL_PRACTICE_NOW_FILE points at a file whose contents are re-read on
    every call so proofs can advance the clock without restarting daemons.
    Production leaves both unset and gets the wall clock.
    """
    raw = os.environ.get("KEEL_PRACTICE_NOW", "").strip()
    if not raw:
        fpath = os.environ.get("KEEL_PRACTICE_NOW_FILE", "").strip()
        if fpath:
            try:
                raw = Path(fpath).read_text(encoding="utf-8").strip()
            except OSError:
                raw = ""
    if not raw:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def practice_now_override() -> datetime | None:
    """practice_now() when a deterministic clock knob is set, else None.

    None means production mode: persistence uses the database's now().
    """
    if os.environ.get("KEEL_PRACTICE_NOW", "").strip():
        return practice_now()
    fpath = os.environ.get("KEEL_PRACTICE_NOW_FILE", "").strip()
    if fpath and Path(fpath).is_file():
        return practice_now()
    return None


# --------------------------------------------------------------------------
# S3.3 — spaced re-check schedule (derived from retrieval_attempts)
# --------------------------------------------------------------------------

# Interval after the stage-1 pass, then after the stage-2 pass. A pass at
# stage 2 retires the seed. Only a pass AT OR AFTER the due instant advances
# the stage; failing a re-check changes nothing (the seed stays due).
RECHECK_INTERVALS = (timedelta(days=3), timedelta(days=7))


def fold_seed_schedule(attempts: list[tuple[bool, datetime]], now: datetime) -> dict[str, Any]:
    """Fold one seed's chronological (passed, created_at) history into a state.

    Returns dict with stage (0=unstarted, 1=first re-check upcoming/due,
    2=second re-check upcoming/due, 3=retired), last_pass_at (the last
    stage-advancing pass), due_at, and status
    ('unstarted' | 'upcoming' | 'due' | 'retired').
    """
    stage = 0
    anchor: datetime | None = None
    for passed, created_at in attempts:
        if not passed:
            continue
        if stage == 0:
            stage = 1
            anchor = created_at
        elif stage == 1 and created_at >= anchor + RECHECK_INTERVALS[0]:
            stage = 2
            anchor = created_at
        elif stage == 2 and created_at >= anchor + RECHECK_INTERVALS[1]:
            stage = 3
            anchor = created_at
    if stage == 0 or anchor is None:
        return {"stage": 0, "status": "unstarted", "last_pass_at": None, "due_at": None}
    if stage >= 3:
        return {"stage": 3, "status": "retired", "last_pass_at": anchor, "due_at": None}
    due_at = anchor + RECHECK_INTERVALS[stage - 1]
    status = "due" if now >= due_at else "upcoming"
    return {"stage": stage, "status": status, "last_pass_at": anchor, "due_at": due_at}


def derive_seed_mastery(
    attempts: list[tuple[bool, datetime]],
    schedule_state: dict[str, Any],
    now: datetime,
) -> str:
    """U5: derive per-seed mastery level:

    unstarted -> attempted -> familiar -> proficient -> mastered,
    with decay on missed or failed re-checks.
    """
    if not attempts:
        return "unstarted"

    stage = schedule_state.get("stage", 0)
    due_at = schedule_state.get("due_at")

    if stage == 0:
        return "attempted"
    elif stage == 1:
        base = "familiar"
    elif stage == 2:
        base = "proficient"
    else:
        base = "mastered"

    if due_at:
        overdue_attempts = [p for p, dt in attempts if dt >= due_at]
        if overdue_attempts and not any(overdue_attempts):
            if base == "mastered":
                return "proficient"
            elif base == "proficient":
                return "familiar"
            elif base == "familiar":
                return "attempted"

        if not overdue_attempts and now >= due_at + timedelta(days=14):
            if base == "mastered":
                return "proficient"
            elif base == "proficient":
                return "familiar"

    return base


# --------------------------------------------------------------------------
# S3.3 — drill token economics: deterministic lesson excerpting
# --------------------------------------------------------------------------

EXCERPT_DEFAULT_CHARS = 3000

_EXCERPT_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this",
    "that", "these", "those", "you", "your", "yours", "we", "our", "they",
    "their", "how", "what", "why", "when", "where", "which", "who", "whom",
    "can", "cannot", "could", "should", "would", "do", "does", "did", "not",
    "no", "as", "at", "from", "into", "over", "under", "than", "then", "so",
    "such", "if", "but", "about", "through", "during", "before", "after",
    "above", "below", "up", "down", "out", "off", "again", "once", "here",
    "there", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "only", "own", "same", "too", "very", "just", "because", "until",
    "while", "versus", "vs", "difference", "between",
})

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")


def excerpt_char_budget() -> int:
    """Char budget for the lesson excerpt. <=0 disables excerpting (full lesson)."""
    raw = os.environ.get("KEEL_RETRIEVAL_EXCERPT_CHARS", "").strip()
    if not raw:
        return EXCERPT_DEFAULT_CHARS
    try:
        return int(raw)
    except ValueError:
        return EXCERPT_DEFAULT_CHARS


_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_SCRIPT_MARKER_RE = re.compile(r"^:::")


def strip_script_markers(markdown_text: str) -> str:
    """Drop a unit script's ':::' marker lines, keeping the prose around them.

    A lesson authored as a unit script uses those lines to tell the page where to
    place the app's own apparatus. They are page structure, not teaching, so no
    judge and no concierge should ever see them. Fence-aware, so a lesson can
    quote a marker inside a code block while explaining the format. A lesson with
    no markers comes back unchanged.
    """
    if ":::" not in markdown_text:
        return markdown_text
    out: list[str] = []
    in_fence = False
    for line in markdown_text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and _SCRIPT_MARKER_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def split_lesson_sections(markdown_text: str) -> list[dict[str, Any]]:
    """Split lesson markdown into heading-anchored sections, in document order.

    Any preamble before the first heading becomes a section with an empty
    heading. Lines inside fenced code blocks are never headings (Python
    comments start with '#'). Stdlib only; no model calls; same result for
    every student.
    """
    sections: list[dict[str, Any]] = []
    heading = ""
    lines: list[str] = []
    in_fence = False
    for line in markdown_text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        if m:
            if lines or heading:
                sections.append({"heading": heading, "body": "\n".join(lines).strip()})
            heading = m.group(1).strip()
            lines = []
        else:
            lines.append(line)
    if lines or heading:
        sections.append({"heading": heading, "body": "\n".join(lines).strip()})
    return sections


def _seed_keywords(seed_prompt: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", seed_prompt.lower())
    return [w for w in words if len(w) >= 3 and w not in _EXCERPT_STOPWORDS]


def _count_keyword(text: str, keyword: str) -> int:
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text.lower()))


def _render_section(sec: dict[str, Any]) -> str:
    if sec["heading"]:
        return ("## " + sec["heading"] + "\n\n" + sec["body"]).strip()
    return sec["body"]


def select_lesson_excerpt(lesson_text: str, seed_prompt: str, budget: int) -> tuple[str, list[str]]:
    """Pick the lesson sections most relevant to the seed under a char budget.

    Deterministic: heading/keyword scoring (heading hits weigh 5x body hits),
    ties broken by document order, chosen sections re-emitted in document
    order. If nothing scores, sections are taken in document order. At least
    one section is always returned (truncated to the budget if needed).
    Returns (excerpt_text, chosen_heading_names).
    """
    sections = split_lesson_sections(lesson_text)
    if not sections:
        return lesson_text[:budget], []
    keywords = _seed_keywords(seed_prompt)
    scored = []
    for order, sec in enumerate(sections):
        distinct = 0
        total = 0
        for kw in keywords:
            hits = 5 * _count_keyword(sec["heading"], kw) + _count_keyword(sec["body"], kw)
            if hits:
                distinct += 1
                total += hits
        # Coverage first: a section touching more distinct seed concepts beats
        # one repeating a single common word (e.g. 'output' in code comments).
        scored.append({"order": order, "sec": sec, "distinct": distinct, "total": total})
    if all(s["distinct"] == 0 for s in scored):
        ranked = sorted(scored, key=lambda s: s["order"])
    else:
        ranked = sorted(scored, key=lambda s: (-s["distinct"], -s["total"], s["order"]))
    chosen: list[tuple[int, str, str]] = []  # (order, rendered_text, heading)
    used = 0
    for cand in ranked:
        text = _render_section(cand["sec"])
        if not chosen:
            if len(text) > budget:
                text = text[: max(0, budget - 6)].rstrip() + "\n[...]"
            chosen.append((cand["order"], text, cand["sec"]["heading"]))
            used = len(text)
            continue
        if used + len(text) + 2 > budget:
            continue
        chosen.append((cand["order"], text, cand["sec"]["heading"]))
        used += len(text) + 2
    chosen.sort(key=lambda c: c[0])
    excerpt = "\n\n".join(c[1] for c in chosen)
    headings = [c[2] for c in chosen if c[2]]
    return excerpt, headings


# --------------------------------------------------------------------------
# S3.4 — adaptive routing: scaffold deep links & derived route state
# --------------------------------------------------------------------------

def get_unit_routing_rules(unit_id: str) -> dict[str, Any] | None:
    """Read unit routing rules from content repo (content/routing/<unit_id>.yaml)."""
    root = content_root()
    matches = sorted(root.glob(f"routing/{unit_id}.yaml"))
    if not matches:
        return None
    try:
        return yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def get_unit_worked_example_scaffold_target(unit_id: str, query: str) -> dict[str, Any]:
    """Map a query (failed seed or completion failure) to a specific worked example target.

    Generalizes the deterministic keyword scoring over the worked example directory:
    README design decisions and individual code files. Heading/title hits weigh 5x body hits.
    Ties broken by document order. Stdlib-only, same result for every student.
    """
    root = content_root()
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    default_target = {
        "target_file": "worked-example",
        "target_section": "Annotated worked example",
        "anchor": "worked-example",
        "url": f"/units/{unit_id}#worked-example",
        "summary": "Review the worked example reference solution.",
        "action_label": "Review worked example",
    }
    if not matches:
        return default_target
    try:
        unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return default_target

    we_rel = (unit_data.get("practice") or {}).get("worked_example")
    if not we_rel:
        return default_target
    we_path = resolve_unit_ref(matches[0], we_rel)
    if we_path is None:
        return default_target
    # The ref may name the README itself; the targets walk its directory.
    we_dir = we_path if we_path.is_dir() else we_path.parent
    if not we_dir.is_dir():
        return default_target

    targets: list[dict[str, Any]] = []
    order = 0

    # README design decisions
    readme_path = we_dir / "README.md"
    if readme_path.is_file():
        try:
            readme_text = readme_path.read_text(encoding="utf-8")
            decisions = re.findall(r"(\d+\.\s+\*\*([^*]+)\*\*\.?\s*([^\n]+(?:\n[^\n\d]+)*))", readme_text)
            for full, title, body in decisions:
                clean_title = title.strip().rstrip(".")
                targets.append({
                    "order": order,
                    "target_file": "README.md",
                    "target_section": f"Design decision: {clean_title}",
                    "anchor": "worked-example",
                    "title": f"Design decision {clean_title}",
                    "text": f"{clean_title}\n{body}",
                    "summary": f'Study design decision "{clean_title}" in the worked example README.',
                    "action_label": "Review scaffold and retry drill",
                })
                order += 1
        except Exception:
            pass

    # Code files
    for p in sorted(we_dir.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if p.name == "schemas.py":
                desc = "InvoiceExtraction schema contract in schemas.py"
                summary = "Study the Pydantic schema contract and JSON Schema derivation in schemas.py."
            elif p.name == "extractor.py":
                desc = "Extraction pipeline and fallback handling in extractor.py"
                summary = "Study the extraction pipeline, error validation, and fallback object construction in extractor.py."
            elif p.name == "llm.py":
                desc = "Constrained generation adapter in llm.py"
                summary = "Study the provider adapter, structured output guarantees, and JSON formatting in llm.py."
            elif p.name == "test_extractor.py":
                desc = "Property tests and verification in test_extractor.py"
                summary = "Study the test assertions for conservation and fallback logging in test_extractor.py."
            elif p.name == "README.md":
                desc = "Worked example overview in README.md"
                summary = "Review the worked example overview and parallel task structure in README.md."
            else:
                desc = f"Reference file {p.name}"
                summary = f"Study {p.name} in the worked example."

            targets.append({
                "order": order,
                "target_file": p.name,
                "target_section": desc,
                "anchor": "worked-example",
                "title": f"{p.name} {desc}",
                "text": content,
                "summary": summary,
                "action_label": "Review scaffold and retry drill",
            })
            order += 1

    if not targets:
        return default_target

    keywords = _seed_keywords(query)
    scored = []
    for t in targets:
        distinct = 0
        total = 0
        for kw in keywords:
            hits = 5 * _count_keyword(t["title"], kw) + _count_keyword(t["text"], kw)
            if hits:
                distinct += 1
                total += hits
        scored.append({"order": t["order"], "distinct": distinct, "total": total, "target": t})

    ranked = sorted(scored, key=lambda s: (-s["distinct"], -s["total"], s["order"]))
    best = ranked[0]["target"] if ranked else targets[0]
    return {
        "target_file": best["target_file"],
        "target_section": best["target_section"],
        "anchor": best["anchor"],
        "url": f"/units/{unit_id}#{best['anchor']}",
        "summary": best["summary"],
        "action_label": best["action_label"],
    }


def get_unit_scaffold_mapping(unit_id: str) -> list[dict[str, Any]]:
    """Get complete scaffold deep link mapping for all retrieval seeds in unit."""
    seeds = get_unit_retrieval_seeds(unit_id)
    mapping = []
    for idx, seed_prompt in enumerate(seeds):
        target = get_unit_worked_example_scaffold_target(unit_id, seed_prompt)
        mapping.append({
            "seed_index": idx,
            "seed_prompt": seed_prompt,
            "target_file": target["target_file"],
            "target_section": target["target_section"],
            "anchor": target["anchor"],
            "url": target["url"],
            "summary": target["summary"],
        })
    return mapping


def derive_unit_practice_route(
    student_id: int,
    unit_id: str,
    is_enrolled: bool,
    retrieval_attempts: list[dict[str, Any]],
    practice_attempts: list[dict[str, Any]],
    seeds: list[str],
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Derive adaptive practice route purely from attempt history (S3.4).

    Honest, side-effect-free, idempotent.
    v1 independence rule: S3.3 spaced re-check due-ness does NOT alter routing
    (keys on pass/fail history only).
    """
    if not is_enrolled:
        return {
            "student_id": student_id,
            "unit_id": unit_id,
            "enrolled": False,
            "status": "unenrolled",
            "recommended_step": None,
            "fast_pass_eligible": False,
            "fast_pass_active": False,
            "scaffold_active": False,
            "summary": "Active enrollment required to view practice route.",
            "steps": [],
            "scaffold_callout": None,
            "scaffold_mapping": [],
        }

    total_seeds = len(seeds)
    seed_history: dict[int, list[bool]] = {i: [] for i in range(total_seeds)}
    for att in retrieval_attempts:
        idx = att.get("seed_index")
        if isinstance(idx, int) and idx in seed_history:
            seed_history[idx].append(bool(att.get("passed", False)))

    passed_seeds: set[int] = set()
    failed_seeds_ever: set[int] = set()
    active_failed_seeds: list[int] = []

    for idx in range(total_seeds):
        history = seed_history[idx]
        has_pass = any(history)
        has_fail = any(not p for p in history)
        if has_pass:
            passed_seeds.add(idx)
        if has_fail:
            failed_seeds_ever.add(idx)
        if has_fail and not has_pass:
            active_failed_seeds.append(idx)

    seeds_passed_count = len(passed_seeds)
    all_seeds_passed = (seeds_passed_count == total_seeds) and total_seeds > 0

    # Fast pass rule (v1): all retrieval seeds passed on first try with no prior failures
    clean_first_try_sweep = all_seeds_passed and (len(failed_seeds_ever) == 0)
    fast_pass_eligible = (len(failed_seeds_ever) == 0)
    fast_pass_active = clean_first_try_sweep

    # Completion problem attempts
    comp_has_pass = any(bool(p.get("passed", False)) for p in practice_attempts)
    comp_has_fail = any(not bool(p.get("passed", False)) for p in practice_attempts)
    comp_latest_failed = len(practice_attempts) > 0 and not comp_has_pass

    # Scaffold remedial condition
    scaffold_active = False
    scaffold_callout: dict[str, Any] | None = None

    if len(active_failed_seeds) > 0:
        scaffold_active = True
        target_seed_idx = active_failed_seeds[-1]
        seed_prompt = seeds[target_seed_idx]
        target_info = get_unit_worked_example_scaffold_target(unit_id, seed_prompt)
        scaffold_callout = {
            "type": "drill_retry",
            "seed_index": target_seed_idx,
            "seed_prompt": seed_prompt,
            "target_file": target_info["target_file"],
            "target_section": target_info["target_section"],
            "anchor": target_info["anchor"],
            "url": target_info["url"],
            "summary": f"Retrieval drill #{target_seed_idx + 1} did not pass. Study {target_info['target_file']} before retrying.",
            "action_label": "Review scaffold and retry drill",
        }
    elif comp_latest_failed:
        scaffold_active = True
        target_info = get_unit_worked_example_scaffold_target(unit_id, "completion problem gap tests failed schemas.py extractor.py fallback")
        scaffold_callout = {
            "type": "completion_retry",
            "target_file": target_info["target_file"],
            "target_section": target_info["target_section"],
            "anchor": target_info["anchor"],
            "url": target_info["url"],
            "summary": f"Completion problem checks did not pass. Study {target_info['target_file']} before retrying.",
            "action_label": "Review scaffold and retry workbench",
        }

    # Step statuses
    # 1. Lesson
    step_lesson_status = "done"
    step_lesson_summary = "Lesson concepts available for review."

    # 2. Retrieval
    if all_seeds_passed:
        step_retrieval_status = "done"
        step_retrieval_summary = f"All {total_seeds} retrieval checkpoints cleared."
    elif len(active_failed_seeds) > 0:
        step_retrieval_status = "retry"
        step_retrieval_summary = f"{seeds_passed_count} of {total_seeds} seeds cleared. Drill #{active_failed_seeds[-1] + 1} requires review."
    else:
        step_retrieval_status = "current"
        step_retrieval_summary = f"{seeds_passed_count} of {total_seeds} retrieval checkpoints cleared."

    # 3. Worked example
    if comp_has_pass:
        step_we_status = "optional" if fast_pass_active else "done"
        step_we_summary = "Worked example completed." if not fast_pass_active else "Optional via fast pass."
    elif scaffold_active:
        step_we_status = "scaffold"
        step_we_summary = "Recommended scaffold review for current failure."
    elif fast_pass_active:
        step_we_status = "optional"
        step_we_summary = "Optional: fast pass achieved via clean retrieval sweep."
    elif all_seeds_passed:
        step_we_status = "current"
        step_we_summary = "Recommended study before attempting the completion problem."
    else:
        step_we_status = "upcoming"
        step_we_summary = "Recommended sequence after retrieval drills."

    # 4. Completion
    if comp_has_pass:
        step_comp_status = "done"
        step_comp_summary = "Completion problem checks passed."
    elif comp_latest_failed:
        step_comp_status = "retry"
        step_comp_summary = "Checks failed. Review scaffold and retry."
    elif fast_pass_active:
        step_comp_status = "current"
        step_comp_summary = "Current recommended action: solve completion problem."
    elif all_seeds_passed:
        step_comp_status = "upcoming"
        step_comp_summary = "Workbench available after reviewing worked example."
    else:
        step_comp_status = "upcoming"
        step_comp_summary = "Workbench available after retrieval drills."

    steps = [
        {"id": "lesson", "title": "Study the lesson", "type": "concept", "status": step_lesson_status, "summary": step_lesson_summary},
        {"id": "retrieval", "title": "Retrieval drills", "type": "drill", "status": step_retrieval_status, "passed_count": seeds_passed_count, "total_count": total_seeds, "summary": step_retrieval_summary},
        {"id": "worked_example", "title": "Annotated worked example", "type": "scaffold", "status": step_we_status, "summary": step_we_summary},
        {"id": "completion", "title": "Completion problem workbench", "type": "workbench", "status": step_comp_status, "summary": step_comp_summary},
    ]

    # Overall route status & recommendation
    if comp_has_pass:
        status = "completed"
        recommended_step = "build"
        summary = "Practice route complete. You are ready to start the Build deliverable."
    elif scaffold_active:
        status = "scaffold_active"
        recommended_step = "worked_example"
        summary = scaffold_callout["summary"] if scaffold_callout else "Review the worked example scaffold before retrying."
    elif fast_pass_active:
        status = "fast_pass"
        recommended_step = "completion"
        summary = "All retrieval drills cleared on first attempt. Worked example is optional. Recommended next: solve the completion problem."
    elif all_seeds_passed:
        status = "standard"
        recommended_step = "worked_example"
        summary = "Retrieval drills cleared. Recommended next: study the worked example before attempting the completion problem."
    else:
        status = "in_progress"
        recommended_step = "retrieval"
        summary = f"Recommended next: complete retrieval drills ({seeds_passed_count} of {total_seeds} cleared)."

    return {
        "student_id": student_id,
        "unit_id": unit_id,
        "enrolled": True,
        "status": status,
        "recommended_step": recommended_step,
        "fast_pass_eligible": fast_pass_eligible,
        "fast_pass_active": fast_pass_active,
        "scaffold_active": scaffold_active,
        "summary": summary,
        "steps": steps,
        "scaffold_callout": scaffold_callout,
        "scaffold_mapping": get_unit_scaffold_mapping(unit_id),
    }


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    tier = next(
        (v for k, v in MODEL_PRICES.items() if model == k or model.startswith(k + "-")),
        {"price_in": 0.15, "price_out": 0.60},
    )
    return (prompt_tokens * tier["price_in"] + completion_tokens * tier["price_out"]) / 1_000_000


def _append_trace(record: dict[str, Any]) -> None:
    dest_str = os.environ.get("KEEL_TRACE_LOG")
    if dest_str is not None:
        dest_str = dest_str.strip()
        if not dest_str or dest_str.lower() == "off":
            return
        dest_path = Path(dest_str)
    else:
        dest_path = Path.home() / ".keelacademy-traces.jsonl"
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        sys.stderr.write(f"[trace] warning: failed to write trace record: {exc}\n")


def _log_trace_call(
    call_id: str,
    attempt: int,
    model: str,
    messages: list[dict[str, str]],
    latency_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    response: str | None = None,
    error: str | None = None,
    caller: str = "retrieval",
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "caller": caller,
        "model": model,
        "tier": "low",
        "attempt": attempt,
        "latency_s": round(latency_s, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(_estimate_cost(model, prompt_tokens, completion_tokens), 6),
        "prompt": messages,
        "response": response,
        "error": error,
        "call_id": call_id,
    }
    _append_trace(record)


def extract_verdict_json(text: str) -> dict[str, Any]:
    """Parse model JSON response, tolerating markdown code fences."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = m.group(1) if m else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in reply")
    parsed = json.loads(candidate[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON is not a dictionary")
    verdict = str(parsed.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "fail"):
        raise ValueError(f"invalid verdict value: {verdict!r}")
    feedback = str(parsed.get("feedback", "")).strip()
    evidence = str(parsed.get("evidence", "")).strip()
    return {
        "verdict": verdict,
        "feedback": feedback,
        "evidence": evidence,
    }


def grade_retrieval_answer(
    student_id: int,
    unit_id: str,
    seed_index: int,
    seed_prompt: str,
    student_answer: str,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Call LLM proxy with per-student budget, Layer-2 retrieval judge prompt,
    nudge retry on malformed JSON, and S1.7 trace logging.

    S3.3: the lesson reaches the judge as a deterministic excerpt (heading/
    keyword section scoring under KEEL_RETRIEVAL_EXCERPT_CHARS; <=0 sends the
    full lesson). The excerpt header line below is part of the prompt, so the
    trace record itself carries the auditable chars-sent metadata.

    Returns (verdict_dict, tokens_charged, excerpt_meta).
    """
    prompt_instructions = get_retrieval_prompt_text(unit_id)
    learn_text = get_unit_learn_text(unit_id)

    budget = excerpt_char_budget()
    if budget > 0 and len(learn_text) > budget:
        lesson_body, excerpt_sections = select_lesson_excerpt(learn_text, seed_prompt, budget)
    else:
        lesson_body, excerpt_sections = learn_text, []
    excerpt_meta = {
        "lesson_chars": len(learn_text),
        "excerpt_chars": len(lesson_body),
        "excerpt_sections": excerpt_sections,
    }
    if excerpt_sections:
        lesson_header = (
            f"Lesson Material (excerpt: {len(lesson_body)} of {len(learn_text)} chars; "
            f"sections: {' | '.join(excerpt_sections)}):"
        )
    else:
        lesson_header = f"Lesson Material (full lesson: {len(learn_text)} chars):"

    user_content = (
        f"{lesson_header}\n{lesson_body}\n\n"
        f"Retrieval Concept Prompt (Question #{seed_index + 1}):\n{seed_prompt}\n\n"
        f"Student Answer:\n<student_answer>\n{student_answer}\n</student_answer>"
    )

    base_messages = [
        {"role": "system", "content": prompt_instructions},
        {"role": "user", "content": user_content},
    ]

    proxy_url = os.environ.get("KEEL_PROXY_URL") or os.environ.get("KEEL_LLM_BASE_URL")
    if proxy_url:
        if not proxy_url.endswith("/v1"):
            proxy_url = proxy_url.rstrip("/") + "/v1"
        endpoint = proxy_url.rstrip("/") + "/chat/completions"
    else:
        endpoint = "http://127.0.0.1:8788/v1/chat/completions"

    model = os.environ.get("KEEL_RETRIEVAL_MODEL", "gpt-4o-mini")
    call_id = f"retrieval-{student_id}-{uuid.uuid4().hex[:8]}"
    total_tokens_charged = 0
    current_messages = list(base_messages)

    for attempt in (1, 2):
        req_body = json.dumps({
            "model": model,
            "messages": current_messages,
            "temperature": 0,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Keel-Student-Id": str(student_id),
        }
        key = os.environ.get("OPENAI_API_KEY")
        if key and "api.openai.com" in endpoint:
            headers["Authorization"] = f"Bearer {key}"

        req = urllib.request.Request(endpoint, data=req_body, headers=headers, method="POST")
        start = time.monotonic()

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
                resp_raw = resp.read()
        except urllib.error.HTTPError as exc:
            latency = time.monotonic() - start
            err_body = exc.read().decode(errors="replace")
            _log_trace_call(
                call_id=call_id,
                attempt=attempt,
                model=model,
                messages=current_messages,
                latency_s=latency,
                error=f"API HTTP {exc.code}: {err_body[:500]}",
            )
            if exc.code == 429:
                raise BudgetExceeded("token budget exceeded") from exc
            raise UpstreamError(f"proxy returned HTTP {exc.code}: {err_body[:500]}") from exc
        except Exception as exc:
            latency = time.monotonic() - start
            _log_trace_call(
                call_id=call_id,
                attempt=attempt,
                model=model,
                messages=current_messages,
                latency_s=latency,
                error=f"API connection error: {exc}",
            )
            raise UpstreamError(f"proxy connection failed: {exc}") from exc

        latency = time.monotonic() - start
        try:
            resp_data = json.loads(resp_raw.decode("utf-8"))
        except Exception as exc:
            raise UpstreamError(f"bad upstream JSON response: {exc}") from exc

        usage = resp_data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens_charged += (prompt_tokens + completion_tokens)

        choices = resp_data.get("choices") or []
        if not choices or "message" not in choices[0]:
            raise UpstreamError("no message choices in upstream response")

        reply_text = choices[0]["message"].get("content", "")

        _log_trace_call(
            call_id=call_id,
            attempt=attempt,
            model=resp_data.get("model", model),
            messages=current_messages,
            latency_s=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response=reply_text,
        )

        try:
            verdict = extract_verdict_json(reply_text)
            return verdict, total_tokens_charged, excerpt_meta
        except Exception as exc:
            if attempt == 2:
                raise MalformedJudgeError(
                    f"judge returned malformed JSON twice: {exc}; last reply: {reply_text[:200]}"
                ) from exc
            # One nudge retry
            current_messages = current_messages + [
                {"role": "assistant", "content": reply_text},
                {"role": "user", "content": NUDGE_MSG},
            ]

def load_unit_rubric(unit_id: str) -> dict[str, Any]:
    """Load the unit rubric spec (S0.4 contract) for conceptual grading.

    Resolution: unit.yaml verify.rubric (relative to content root), falling back
    to rubrics/<unit_id>/v1.yaml. A missing, unreadable, or criteria-less rubric
    is a hard error — grading never silently falls back to an unvalidated
    contract.

    Returns {"text", "pass_rule", "criteria_ids"}.
    """
    root = content_root()
    rubric_path: Path | None = None
    matches = sorted(root.glob(f"units/*/{unit_id}/unit.yaml"))
    if matches:
        try:
            unit_data = yaml.safe_load(matches[0].read_text(encoding="utf-8"))
            rubric_rel = (unit_data.get("verify") or {}).get("rubric")
            if isinstance(rubric_rel, str) and rubric_rel:
                candidate = root / rubric_rel
                if candidate.is_file():
                    rubric_path = candidate
        except Exception:
            pass
    if rubric_path is None:
        candidate = root / "rubrics" / unit_id / "v1.yaml"
        if candidate.is_file():
            rubric_path = candidate
    if rubric_path is None:
        raise RubricError(f"no rubric found for unit {unit_id}")
    try:
        rubric = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
        assert isinstance(rubric, dict)
    except Exception as exc:
        raise RubricError(f"unreadable rubric for unit {unit_id}: {exc}") from exc
    criteria_ids = [
        c["id"] for c in (rubric.get("criteria") or [])
        if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"].strip()
    ]
    if not criteria_ids:
        raise RubricError(f"rubric for unit {unit_id} declares no criteria")
    return {
        "text": rubric_path.read_text(encoding="utf-8"),
        "pass_rule": rubric.get("pass_rule"),
        "criteria_ids": criteria_ids,
    }


def get_conceptual_judge_prompt(unit_id: str) -> str:
    """Read conceptual completion judge prompt template from content/prompts/,
    substituting the unit rubric verbatim over the RUBRIC_INSERT marker (same
    contract as the S0.x CLI grader) — the judge cannot grade against criteria
    it never sees."""
    root = content_root()
    prompts_dir = root / "prompts"
    unit_prompt = prompts_dir / f"judge-{unit_id}.md"
    general_prompt = prompts_dir / "judge-conceptual.md"
    template: str
    if unit_prompt.is_file():
        template = unit_prompt.read_text(encoding="utf-8")
    elif general_prompt.is_file():
        template = general_prompt.read_text(encoding="utf-8")
    else:
        # Fallback to retrieval prompt template if specific judge prompt not found
        return get_retrieval_prompt_text(unit_id)
    if RUBRIC_INSERT_RE.search(template):
        template = RUBRIC_INSERT_RE.sub(lambda _: load_unit_rubric(unit_id)["text"].strip(), template)
    return template


def extract_conceptual_verdict_json(text: str, rubric: dict[str, Any]) -> dict[str, Any]:
    """Parse a conceptual judge reply against the rubric criteria-array contract.

    Contract (content/prompts/judge-0.*.md output format):
      {"unit": "...", "criteria": [{"id", "verdict", "evidence"}, ...],
       "overall": "pass"|"fail", "overall_rationale": "..."}

    Validation rules — any violation is a hard error (the S0.4 rule: never
    silently reconcile):
      - reply must contain one JSON object (markdown fences tolerated)
      - "criteria" must be a non-empty array of objects
      - every criterion id must exist in the unit rubric, every rubric criterion
        must appear exactly once (unknown, missing, or duplicate id -> error)
      - every verdict must be "pass" or "fail"; evidence must be a string
    The model's own "overall" is discarded: the platform recomputes the overall
    by applying the rubric's pass_rule ("all" -> pass iff every criterion
    passes; any other rule is a hard error while undefined by the schema).
    """
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = m.group(1) if m else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in reply")
    try:
        parsed = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON is not a dictionary")
    criteria_raw = parsed.get("criteria")
    if not isinstance(criteria_raw, list) or not criteria_raw:
        raise ValueError("missing or empty criteria array")
    expected_ids = list(rubric["criteria_ids"])
    verdicts: dict[str, dict[str, str]] = {}
    for crit in criteria_raw:
        if not isinstance(crit, dict):
            raise ValueError("criterion entry is not a JSON object")
        crit_id = str(crit.get("id", "")).strip()
        if crit_id not in expected_ids:
            raise ValueError(f"criterion id diverges from rubric: {crit_id!r}")
        if crit_id in verdicts:
            raise ValueError(f"duplicate criterion id: {crit_id!r}")
        crit_verdict = str(crit.get("verdict", "")).strip().lower()
        if crit_verdict not in ("pass", "fail"):
            raise ValueError(f"invalid verdict for criterion {crit_id!r}: {crit_verdict!r}")
        evidence = crit.get("evidence", "")
        if not isinstance(evidence, str):
            raise ValueError(f"evidence for criterion {crit_id!r} is not a string")
        verdicts[crit_id] = {"verdict": crit_verdict, "evidence": evidence.strip()}
    missing = [cid for cid in expected_ids if cid not in verdicts]
    if missing:
        raise ValueError(f"rubric criteria missing from judge reply: {missing}")

    pass_rule = rubric.get("pass_rule")
    if pass_rule != "all":
        raise ValueError(f"unsupported rubric pass_rule: {pass_rule!r}")
    overall = "pass" if all(v["verdict"] == "pass" for v in verdicts.values()) else "fail"
    return {
        "overall": overall,
        "feedback": str(parsed.get("overall_rationale", "")).strip(),
        "criteria": [{"id": cid, **verdicts[cid]} for cid in expected_ids],
    }


def conceptual_submission_facts(student_answer: str) -> str:
    """Platform-computed facts about a conceptual submission.

    Word counts and heading lists are exactly the things an LLM judge counts
    badly, and exactly the things format criteria hinge on. The platform
    computes them deterministically; the judge prompt tells the model to trust
    these numbers over its own counting. Unit-agnostic: no content lives here.
    """
    word_count = len(student_answer.split())
    headings = [line.rstrip() for line in student_answer.splitlines() if line.startswith("##")]
    lines = [
        "Deterministic Submission Facts (computed by the platform; authoritative,",
        "use these instead of counting yourself):",
        f"- word_count: {word_count}",
        f"- markdown_headings_found (every line starting with ##): {len(headings)}",
    ]
    for h in headings:
        lines.append(f"  - {h}")
    return "\n".join(lines)


def grade_conceptual_completion_answer(
    student_id: int,
    unit_id: str,
    prompt: str,
    instructions: str,
    student_answer: str,
) -> tuple[dict[str, Any], int]:
    """Call LLM proxy to grade conceptual completion answer against the unit rubric.

    Fails fast on a missing/invalid rubric (before any model spend). The reply
    is parsed against the rubric criteria-array contract with per-criterion
    validation and a platform-computed overall (see extract_conceptual_verdict_json).

    Returns (verdict_dict, tokens_charged) where verdict_dict is
    {"overall", "feedback", "criteria": [{"id", "verdict", "evidence"}, ...]}.
    """
    rubric = load_unit_rubric(unit_id)
    prompt_instructions = get_conceptual_judge_prompt(unit_id)
    learn_text = get_unit_learn_text(unit_id)

    budget = excerpt_char_budget()
    if budget > 0 and len(learn_text) > budget:
        lesson_body, excerpt_sections = select_lesson_excerpt(learn_text, prompt, budget)
    else:
        lesson_body, excerpt_sections = learn_text, []

    if excerpt_sections:
        lesson_header = (
            f"Lesson Material (excerpt: {len(lesson_body)} of {len(learn_text)} chars; "
            f"sections: {' | '.join(excerpt_sections)}):"
        )
    else:
        lesson_header = f"Lesson Material (full lesson: {len(learn_text)} chars):"

    user_content = (
        f"{lesson_header}\n{lesson_body}\n\n"
        f"Conceptual Problem Prompt:\n{prompt}\n\n"
        f"Instructions:\n{instructions}\n\n"
        f"Student Submission:\n<student_answer>\n{student_answer}\n</student_answer>\n\n"
        f"{conceptual_submission_facts(student_answer)}"
    )

    base_messages = [
        {"role": "system", "content": prompt_instructions},
        {"role": "user", "content": user_content},
    ]

    proxy_url = os.environ.get("KEEL_PROXY_URL") or os.environ.get("KEEL_LLM_BASE_URL")
    if proxy_url:
        if not proxy_url.endswith("/v1"):
            proxy_url = proxy_url.rstrip("/") + "/v1"
        endpoint = proxy_url.rstrip("/") + "/chat/completions"
    else:
        endpoint = "http://127.0.0.1:8788/v1/chat/completions"

    model = os.environ.get("KEEL_COMPLETION_MODEL") or os.environ.get("KEEL_JUDGE_MODEL", "gpt-4o-mini")
    call_id = f"completion-{student_id}-{uuid.uuid4().hex[:8]}"
    total_tokens_charged = 0
    current_messages = list(base_messages)

    for attempt in (1, 2):
        req_body = json.dumps({
            "model": model,
            "messages": current_messages,
            "temperature": 0,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Keel-Student-Id": str(student_id),
        }
        key = os.environ.get("OPENAI_API_KEY")
        if key and "api.openai.com" in endpoint:
            headers["Authorization"] = f"Bearer {key}"

        req = urllib.request.Request(endpoint, data=req_body, headers=headers, method="POST")
        start = time.monotonic()

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
                resp_raw = resp.read()
        except urllib.error.HTTPError as exc:
            latency = time.monotonic() - start
            err_body = exc.read().decode(errors="replace")
            _log_trace_call(
                call_id=call_id,
                attempt=attempt,
                model=model,
                messages=current_messages,
                latency_s=latency,
                error=f"API HTTP {exc.code}: {err_body[:500]}",
                caller="completion",
            )
            if exc.code == 429:
                raise BudgetExceeded("token budget exceeded") from exc
            raise UpstreamError(f"proxy returned HTTP {exc.code}: {err_body[:500]}") from exc
        except Exception as exc:
            latency = time.monotonic() - start
            _log_trace_call(
                call_id=call_id,
                attempt=attempt,
                model=model,
                messages=current_messages,
                latency_s=latency,
                error=f"API connection error: {exc}",
                caller="completion",
            )
            raise UpstreamError(f"proxy connection failed: {exc}") from exc

        latency = time.monotonic() - start
        try:
            resp_data = json.loads(resp_raw.decode("utf-8"))
        except Exception as exc:
            raise UpstreamError(f"bad upstream JSON response: {exc}") from exc

        usage = resp_data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens_charged += (prompt_tokens + completion_tokens)

        choices = resp_data.get("choices") or []
        if not choices or "message" not in choices[0]:
            raise UpstreamError("no message choices in upstream response")

        reply_text = choices[0]["message"].get("content", "")

        _log_trace_call(
            call_id=call_id,
            attempt=attempt,
            model=resp_data.get("model", model),
            messages=current_messages,
            latency_s=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response=reply_text,
            caller="completion",
        )

        try:
            verdict = extract_conceptual_verdict_json(reply_text, rubric)
            return verdict, total_tokens_charged
        except Exception as exc:
            if attempt == 2:
                raise MalformedJudgeError(
                    f"judge reply violated the rubric criteria contract twice: {exc}; last reply: {reply_text[:200]}"
                ) from exc
            # One nudge retry
            current_messages = current_messages + [
                {"role": "assistant", "content": reply_text},
                {"role": "user", "content": NUDGE_MSG},
            ]

    raise MalformedJudgeError("unreachable")


# --------------------------------------------------------------------------
# S3.5 — concierge v1: server-side teach/guard mode switch & proxy routing
# --------------------------------------------------------------------------

def derive_concierge_mode(route_status: str | None, recommended_step: str | None = None) -> tuple[str, str]:
    """Derive concierge mode and reason from route status and step (S3.5).

    Rule: completed -> guard, otherwise teach.
    """
    if route_status == "completed":
        return "guard", "Practice route completed (build context): Socratic unblocking active; deliverable generation refused."
    step = recommended_step or "practice"
    return "teach", f"Practice route in progress ({step} context): free explanation and micro-exercises active."


def compose_concierge_messages(unit_id: str, question: str, mode: str = "guard") -> list[dict[str, str]]:
    """Compose the exact system and user messages for a concierge query (S3.5, S3.6)."""
    if mode == "teach":
        prompt_instructions = get_concierge_teach_prompt(unit_id)
        learn_text = get_unit_learn_text(unit_id)
        budget = excerpt_char_budget()
        if budget > 0 and len(learn_text) > budget:
            excerpt_body, excerpt_sections = select_lesson_excerpt(learn_text, question, budget)
        else:
            excerpt_body, excerpt_sections = learn_text, []
        if excerpt_sections:
            lesson_header = (
                f"Lesson Material (excerpt: {len(excerpt_body)} of {len(learn_text)} chars; "
                f"sections: {' | '.join(excerpt_sections)}):"
            )
        else:
            lesson_header = f"Lesson Material (full lesson: {len(learn_text)} chars):"

        parts = [f"{lesson_header}\n{excerpt_body}"]
        faq_text = get_unit_faq_text(unit_id)
        if faq_text:
            parts.append(f"Unit FAQ and Unstuck Context:\n{faq_text}")
        parts.append(f"Student Question:\n<student_question>\n{question.strip()}\n</student_question>")
        user_content = "\n\n".join(parts)
    else:
        prompt_instructions = get_concierge_guard_prompt(unit_id)
        deliverable_text, rubric_summary = get_unit_guard_context(unit_id)
        parts = [
            f"Unit Deliverable Specification:\n{deliverable_text}",
            f"Grading Rubric Criteria (What is Graded):\n{rubric_summary}",
            f"Student Question:\n<student_question>\n{question.strip()}\n</student_question>",
        ]
        user_content = "\n\n".join(parts)

    return [
        {"role": "system", "content": prompt_instructions},
        {"role": "user", "content": user_content},
    ]


def ask_concierge(
    student_id: int,
    unit_id: str,
    question: str,
) -> tuple[str, str, str, int]:
    """Derive mode from student route state, compose prompt, call proxy, and return
    (mode, mode_reason, answer, tokens_charged).
    """
    # 1. Query attempt history (read-only, wrapped in BEGIN/ROLLBACK)
    attempts_sql = """BEGIN;
SELECT 'retrieval' AS kind, id, seed_index, (passed = 't')::text, 0 AS pass_count, 0 AS total_checks, created_at::text
FROM retrieval_attempts
WHERE student_id = %d AND unit_id = %s
UNION ALL
SELECT 'practice' AS kind, id, -1 AS seed_index, (passed = 't')::text, pass_count, total_checks, created_at::text
FROM practice_attempts
WHERE student_id = %d AND unit_id = %s
ORDER BY 1, 2 ASC;
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id, sql_str(unit_id))
    try:
        rows = db_sql(attempts_sql)
    except Exception as exc:
        raise RuntimeError(f"failed to query attempt history: {exc}") from exc

    retrieval_attempts: list[dict[str, Any]] = []
    practice_attempts: list[dict[str, Any]] = []
    for r in rows:
        kind, att_id, s_idx, passed_str, p_count, tot_checks, created_at = r
        passed = (passed_str == "true" or passed_str == "t" or passed_str is True)
        if kind == "retrieval":
            retrieval_attempts.append({
                "id": int(att_id),
                "seed_index": int(s_idx),
                "passed": passed,
                "created_at": created_at,
            })
        else:
            practice_attempts.append({
                "id": int(att_id),
                "passed": passed,
                "pass_count": int(p_count),
                "total_checks": int(tot_checks),
                "created_at": created_at,
            })

    seeds = get_unit_retrieval_seeds(unit_id)
    rules = get_unit_routing_rules(unit_id) or {}
    route_data = derive_unit_practice_route(
        student_id=student_id,
        unit_id=unit_id,
        is_enrolled=True,
        retrieval_attempts=retrieval_attempts,
        practice_attempts=practice_attempts,
        seeds=seeds,
        rules=rules,
    )

    # 2. Derive mode structurally from route state (v1 rule: completed -> guard, otherwise teach)
    mode, mode_reason = derive_concierge_mode(
        route_data.get("status"),
        route_data.get("recommended_step"),
    )

    # 3. Context composition
    messages = compose_concierge_messages(unit_id, question, mode=mode)

    # 4. Call LLM Proxy
    proxy_url = os.environ.get("KEEL_PROXY_URL") or os.environ.get("KEEL_LLM_BASE_URL")
    if proxy_url:
        if not proxy_url.endswith("/v1"):
            proxy_url = proxy_url.rstrip("/") + "/v1"
        endpoint = proxy_url.rstrip("/") + "/chat/completions"
    else:
        endpoint = "http://127.0.0.1:8788/v1/chat/completions"

    model = os.environ.get("KEEL_CONCIERGE_MODEL", "gpt-4o-mini")
    call_id = f"concierge-{student_id}-{uuid.uuid4().hex[:8]}"

    req_body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2 if mode == "teach" else 0.0,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Keel-Student-Id": str(student_id),
    }
    key = os.environ.get("OPENAI_API_KEY")
    if key and "api.openai.com" in endpoint:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(endpoint, data=req_body, headers=headers, method="POST")
    start = time.monotonic()

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
            resp_raw = resp.read()
    except urllib.error.HTTPError as exc:
        latency = time.monotonic() - start
        err_body = exc.read().decode(errors="replace")
        _log_trace_call(
            call_id=call_id,
            attempt=1,
            model=model,
            messages=messages,
            latency_s=latency,
            error=f"API HTTP {exc.code}: {err_body[:500]}",
            caller="concierge",
        )
        if exc.code == 429:
            raise BudgetExceeded("token budget exceeded") from exc
        raise UpstreamError(f"proxy returned HTTP {exc.code}: {err_body[:500]}") from exc
    except Exception as exc:
        latency = time.monotonic() - start
        _log_trace_call(
            call_id=call_id,
            attempt=1,
            model=model,
            messages=messages,
            latency_s=latency,
            error=f"API connection error: {exc}",
            caller="concierge",
        )
        raise UpstreamError(f"proxy connection failed: {exc}") from exc

    latency = time.monotonic() - start
    try:
        resp_data = json.loads(resp_raw.decode("utf-8"))
    except Exception as exc:
        raise UpstreamError(f"bad upstream JSON response: {exc}") from exc

    usage = resp_data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens_charged = prompt_tokens + completion_tokens

    choices = resp_data.get("choices") or []
    if not choices or "message" not in choices[0]:
        raise UpstreamError("no message choices in upstream response")

    answer_text = choices[0]["message"].get("content", "")

    _log_trace_call(
        call_id=call_id,
        attempt=1,
        model=resp_data.get("model", model),
        messages=messages,
        latency_s=latency,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response=answer_text,
        caller="concierge",
    )

    return mode, mode_reason, answer_text, total_tokens_charged


class PracticeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Minimal logging; never log payload bodies
        sys.stderr.write("practice: %s %s\n" % (self.command, self.path))

    def _read_body(self) -> tuple[bool, bytes]:
        """Read Content-Length bytes with a hard cap and guarded parse."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return False, b""
        if length < 0 or length > MAX_BODY_BYTES:
            return False, b""
        return True, self.rfile.read(length) if length else b""

    def _app_authorized(self) -> bool:
        expected = app_token()
        if not expected:
            return False
        supplied = self.headers.get("X-Keel-App-Token", "")
        return hmac.compare_digest(supplied, expected)

    def _bad_token(self) -> None:
        self._respond(401, {"error": "invalid app token"})

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(200, {"ok": True})
            return

        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        # Public routes: /gallery and /gallery/<id> can be queried publicly OR with app token (S4.4)
        is_public_get = (parsed.path == "/gallery" or bool(re.match(r"^/gallery/\d+$", parsed.path)))
        if not is_public_get and not self._app_authorized():
            self._bad_token()
            return

        # Analytics routes (S4.7)
        if parsed.path == "/analytics/summary":
            self._handle_get_analytics_summary()
            return
        if parsed.path == "/analytics/funnel":
            self._handle_get_analytics_funnel()
            return
        if parsed.path in ("/analytics/drop-off", "/analytics/dropoff"):
            self._handle_get_analytics_dropoff(query)
            return
        m_aunit = re.match(r"^/analytics/units/([A-Za-z0-9_.-]+)$", parsed.path)
        if m_aunit:
            self._handle_get_analytics_unit(m_aunit.group(1))
            return

        # GET /gallery (S4.4)
        if parsed.path == "/gallery":
            self._handle_get_gallery(query)
            return
        m_gproj = re.match(r"^/gallery/(\d{1,15})$", parsed.path)
        if m_gproj:
            self._handle_get_gallery_project(int(m_gproj.group(1)))
            return
        m_gsub = re.match(r"^/gallery/submission/(\d{1,15})$", parsed.path)
        if m_gsub:
            self._handle_get_submission_gallery(int(m_gsub.group(1)))
            return
        m_sgall = re.match(r"^/students/(\d{1,15})/gallery$", parsed.path)
        if m_sgall:
            self._handle_get_student_gallery(int(m_sgall.group(1)))
            return
        m_gsid = re.match(r"^/gallery/student/(\d{1,15})$", parsed.path)
        if m_gsid:
            self._handle_get_student_gallery(int(m_gsid.group(1)))
            return

        # GET /simulation/<id> and GET /students/<id>/simulations (S4.5, S4.6)
        m_sim_defenses = re.match(r"^/students/(\d{1,15})/simulations/defenses$", parsed.path)
        if m_sim_defenses:
            self._handle_get_student_defenses(int(m_sim_defenses.group(1)))
            return
        m_sim_detail = re.match(r"^/simulation/(\d{1,15})$", parsed.path)
        if m_sim_detail:
            self._handle_get_simulation(int(m_sim_detail.group(1)), query)
            return
        m_sim_stud = re.match(r"^/students/(\d{1,15})/simulations$", parsed.path)
        if m_sim_stud:
            self._handle_get_student_simulations(int(m_sim_stud.group(1)))
            return
        if parsed.path == "/simulations":
            sid_str = (query.get("student_id") or [""])[0]
            if sid_str.isdigit():
                self._handle_get_student_simulations(int(sid_str))
                return


        # GET /diagnostic/spec?id=<id> (S4.1)
        if parsed.path == "/diagnostic/spec":
            diag_id = (query.get("id") or ["placement-phase-1"])[0]
            self._handle_get_diagnostic_spec(diag_id)
            return

        # GET /pod/members?student_id=<id> OR /students/<id>/pod (S4.2)
        if parsed.path in ("/pod/members", "/pod/detail"):
            sid_str = (query.get("student_id") or [""])[0]
            if not sid_str.isdigit():
                self._respond(400, {"error": "student_id (int) required"})
                return
            self._handle_get_pod_members(int(sid_str))
            return
        m_pod_m = re.match(r"^/students/(\d{1,15})/pod$", parsed.path)
        if m_pod_m:
            self._handle_get_pod_members(int(m_pod_m.group(1)))
            return

        # GET /pod/posts?pod_id=<id>[&week=<week>] (S4.2)
        if parsed.path == "/pod/posts":
            pid_str = (query.get("pod_id") or [""])[0]
            if not pid_str.isdigit():
                self._respond(400, {"error": "pod_id (int) required"})
                return
            week_str = (query.get("week") or query.get("week_number") or [""])[0]
            week_num = int(week_str) if week_str.isdigit() else None
            self._handle_get_pod_posts(int(pid_str), week_num)
            return
        m_pod_p = re.match(r"^/pods/(\d{1,15})/posts$", parsed.path)
        if m_pod_p:
            week_str = (query.get("week") or query.get("week_number") or [""])[0]
            week_num = int(week_str) if week_str.isdigit() else None
            self._handle_get_pod_posts(int(m_pod_p.group(1)), week_num)
            return

        # GET /digest/latest?student_id=<id> (S4.3)
        if parsed.path == "/digest/latest":
            sid_str = (query.get("student_id") or [""])[0]
            if not sid_str.isdigit():
                self._respond(400, {"error": "student_id (int) required"})
                return
            self._handle_get_latest_digest(int(sid_str))
            return
        m_digest = re.match(r"^/students/(\d{1,15})/digest/latest$", parsed.path)
        if m_digest:
            self._handle_get_latest_digest(int(m_digest.group(1)))
            return

        # GET /diagnostic/attempts?student_id=<id> (S4.1)
        if parsed.path == "/diagnostic/attempts":
            sid_str = (query.get("student_id") or [""])[0]
            if not sid_str.isdigit():
                self._respond(400, {"error": "student_id (int) required"})
                return
            self._handle_get_diagnostic_attempts(int(sid_str))
            return
        m_datt = re.match(r"^/students/(\d{1,15})/diagnostic/attempts$", parsed.path)
        if m_datt:
            self._handle_get_diagnostic_attempts(int(m_datt.group(1)))
            return

        # GET /practice/retrieval/seeds?unit=3.2.1 OR /units/<unit_id>/practice/retrieval/seeds
        if parsed.path == "/practice/retrieval/seeds":
            unit_id = (query.get("unit") or [""])[0]
            self._handle_get_retrieval_seeds(unit_id)
            return
        m_rseeds = re.match(r"^/units/(\d+\.\d+\.\d+)/practice/retrieval/seeds$", parsed.path)
        if m_rseeds:
            self._handle_get_retrieval_seeds(m_rseeds.group(1))
            return

        # GET /practice/retrieval/attempts?student_id=<id>&unit=<id> OR /students/<id>/practice/retrieval/attempts
        if parsed.path == "/practice/retrieval/attempts":
            sid_str = (query.get("student_id") or [""])[0]
            uid = (query.get("unit") or [""])[0]
            if not sid_str.isdigit() or not UNIT_RE.match(uid):
                self._respond(400, {"error": "student_id (int) and unit (x.y.z) required"})
                return
            self._handle_get_retrieval_attempts(int(sid_str), uid)
            return
        m_ratt = re.match(r"^/students/(\d{1,15})/practice/retrieval/attempts$", parsed.path)
        if m_ratt:
            sid = int(m_ratt.group(1))
            uid = (query.get("unit") or [""])[0]
            if not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit query parameter required"})
                return
            self._handle_get_retrieval_attempts(sid, uid)
            return

        # GET /practice/retrieval/schedule?student_id=<id>[&unit=<id>] (S3.3)
        if parsed.path == "/practice/retrieval/schedule":
            sid_str = (query.get("student_id") or [""])[0]
            uid = (query.get("unit") or [""])[0]
            if not sid_str.isdigit():
                self._respond(400, {"error": "student_id (int) required"})
                return
            if uid and not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit must be x.y.z when given"})
                return
            self._handle_get_recheck_schedule(int(sid_str), uid or None)
            return
        m_rsched = re.match(r"^/students/(\d{1,15})/practice/retrieval/schedule$", parsed.path)
        if m_rsched:
            sid = int(m_rsched.group(1))
            uid = (query.get("unit") or [""])[0]
            if uid and not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit must be x.y.z when given"})
                return
            self._handle_get_recheck_schedule(sid, uid or None)
            return

        # GET /practice/review/queue?student_id=<id> OR /students/<id>/practice/review/queue (U5)
        if parsed.path == "/practice/review/queue":
            sid_str = (query.get("student_id") or [""])[0]
            if not sid_str.isdigit():
                self._respond(400, {"error": "student_id (int) required"})
                return
            self._handle_get_review_queue(int(sid_str))
            return
        m_rqueue = re.match(r"^/students/(\d{1,15})/practice/review/queue$", parsed.path)
        if m_rqueue:
            self._handle_get_review_queue(int(m_rqueue.group(1)))
            return

        # GET /practice/route?student_id=<id>&unit=<id> OR /students/<id>/practice/route (S3.4)
        if parsed.path == "/practice/route":
            sid_str = (query.get("student_id") or [""])[0]
            uid = (query.get("unit") or [""])[0]
            if not sid_str.isdigit() or not UNIT_RE.match(uid):
                self._respond(400, {"error": "student_id (int) and unit (x.y.z) required"})
                return
            self._handle_get_practice_route(int(sid_str), uid)
            return
        m_route = re.match(r"^/students/(\d{1,15})/practice/route$", parsed.path)
        if m_route:
            sid = int(m_route.group(1))
            uid = (query.get("unit") or [""])[0]
            if not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit query parameter required"})
                return
            self._handle_get_practice_route(sid, uid)
            return

        # GET /practice/manifest?unit=3.2.1 OR /units/<unit_id>/practice/manifest
        unit_id = None
        if parsed.path == "/practice/manifest":
            unit_id = (query.get("unit") or [""])[0]
        else:
            m_unit = re.match(r"^/units/(\d+\.\d+\.\d+)/practice/manifest$", parsed.path)
            if m_unit:
                unit_id = m_unit.group(1)

        if unit_id is not None:
            self._handle_get_manifest(unit_id)
            return

        # GET /concierge/turns?student_id=<id>&unit=<id> OR /students/<id>/concierge/turns (S3.5)
        if parsed.path == "/concierge/turns":
            sid_str = (query.get("student_id") or [""])[0]
            uid = (query.get("unit") or [""])[0]
            if not sid_str.isdigit() or not UNIT_RE.match(uid):
                self._respond(400, {"error": "student_id (int) and unit (x.y.z) required"})
                return
            self._handle_get_concierge_turns(int(sid_str), uid)
            return
        m_cturns = re.match(r"^/students/(\d{1,15})/concierge/turns$", parsed.path)
        if m_cturns:
            sid = int(m_cturns.group(1))
            uid = (query.get("unit") or [""])[0]
            if not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit query parameter required"})
                return
            self._handle_get_concierge_turns(sid, uid)
            return

        # GET /practice/attempts?student_id=<id>&unit=<id> OR /students/<id>/practice/attempts
        if parsed.path == "/practice/attempts":
            sid_str = (query.get("student_id") or [""])[0]
            uid = (query.get("unit") or [""])[0]
            if not sid_str.isdigit() or not UNIT_RE.match(uid):
                self._respond(400, {"error": "student_id (int) and unit (x.y.z) required"})
                return
            self._handle_get_attempts(int(sid_str), uid)
            return

        m_att = re.match(r"^/students/(\d{1,15})/practice/attempts$", parsed.path)
        if m_att:
            sid = int(m_att.group(1))
            uid = (query.get("unit") or [""])[0]
            if not UNIT_RE.match(uid):
                self._respond(400, {"error": "unit query parameter required"})
                return
            self._handle_get_attempts(sid, uid)
            return

        self._respond(404, {"error": "not found"})

    def _handle_get_concierge_turns(self, student_id: int, unit_id: str) -> None:
        sql = """BEGIN;
SELECT id, student_id, unit_id, mode, question, answer, tokens_charged, created_at::text
FROM concierge_turns
WHERE student_id = %d AND unit_id = %s
ORDER BY id ASC
LIMIT 100;
ROLLBACK;
""" % (student_id, sql_str(unit_id))
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        turns = []
        for r in rows:
            turns.append({
                "id": int(r[0]),
                "student_id": int(r[1]),
                "unit_id": r[2],
                "mode": r[3],
                "question": r[4],
                "answer": r[5],
                "tokens_charged": int(r[6]),
                "created_at": str(r[7]),
            })
        self._respond(200, {"turns": turns})

    def _handle_get_diagnostic_spec(self, diagnostic_id: str) -> None:
        spec = get_diagnostic_spec(diagnostic_id)
        if not spec:
            self._respond(404, {"error": "diagnostic_spec_not_found"})
            return
        # Return public spec (omit correct_answer and explanation for student clients)
        client_questions = []
        for q in spec.get("questions", []):
            client_questions.append({
                "id": q.get("id"),
                "category": q.get("category"),
                "type": q.get("type"),
                "prompt": q.get("prompt"),
                "points": q.get("points"),
                "options": q.get("options"),
            })
        self._respond(200, {
            "id": spec.get("id"),
            "title": spec.get("title"),
            "est_minutes": spec.get("est_minutes"),
            "passing_threshold_pct": spec.get("passing_threshold_pct"),
            "pass_skip_units": spec.get("pass_skip_units"),
            "fail_baseline_units": spec.get("fail_baseline_units"),
            "categories": spec.get("categories"),
            "questions": client_questions,
        })

    def _handle_get_diagnostic_attempts(self, student_id: int) -> None:
        sql = """BEGIN;
SELECT id, student_id, diagnostic_id, passed, score_pct, points_earned, points_possible,
       route, answers_json::text, breakdown_json::text, created_at
FROM diagnostic_attempts
WHERE student_id = %d
ORDER BY id DESC
LIMIT 50;
ROLLBACK;
""" % student_id
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        attempts = []
        for r in rows:
            attempts.append({
                "id": int(r[0]),
                "student_id": int(r[1]),
                "diagnostic_id": r[2],
                "passed": r[3] == "t" or r[3] is True,
                "score_pct": float(r[4]),
                "points_earned": int(r[5]),
                "points_possible": int(r[6]),
                "route": r[7],
                "answers": json.loads(r[8]),
                "breakdown": json.loads(r[9]),
                "created_at": str(r[10]),
            })
        self._respond(200, {"student_id": student_id, "attempts": attempts})

    def _handle_diagnostic_opt_out(self) -> None:
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        diagnostic_id = payload.get("diagnostic_id") or "placement-phase-1"

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return

        spec = get_diagnostic_spec(diagnostic_id)
        if not spec:
            self._respond(404, {"error": "diagnostic_spec_not_found"})
            return

        # 1. Verify student exists
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return

        baseline_units = spec.get("fail_baseline_units") or ["0.1", "1.1", "1.2"]
        now_override = practice_now_override()
        created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "now()"

        # Atomic persistence: diagnostic_attempts + spine events + unlocked_units
        units_values = ", ".join(sql_str(u) for u in baseline_units)
        answers_json_str = sql_str(json.dumps({}))
        breakdown_json_str = sql_str(json.dumps([]))
        unlocked_json_str = sql_str(json.dumps(baseline_units))
        persist_sql = f"""BEGIN;
WITH attempt AS (
    INSERT INTO diagnostic_attempts (
        student_id, diagnostic_id, passed, score_pct, points_earned, points_possible,
        route, answers_json, breakdown_json, created_at
    ) VALUES (
        {student_id}, {sql_str(diagnostic_id)}, false, 0.0, 0, {len(spec.get("questions", []))}, 'opt_out', {answers_json_str}::jsonb, {breakdown_json_str}::jsonb, {created_at_sql}
    )
    RETURNING id, student_id, diagnostic_id, passed, score_pct, route, created_at
), ins AS (
    INSERT INTO unlocked_units (student_id, unit_id, gate_id, unlocked_at, source_event_seq)
    SELECT {student_id}, u, {sql_str("diagnostic-opt-out")}, {created_at_sql}, (SELECT id FROM attempt)
    FROM unnest(ARRAY[{units_values}]::text[]) u
    ON CONFLICT (student_id, unit_id) DO NOTHING
    RETURNING student_id, unit_id, unlocked_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'diagnostic.placed',
           jsonb_build_object(
               'attempt_id', id,
               'student_id', student_id,
               'diagnostic_id', diagnostic_id,
               'passed', false,
               'score_pct', score_pct,
               'route', route,
               'opt_out', true,
               'unlocked_units', {unlocked_json_str}::jsonb
           )
    FROM attempt
    RETURNING id
)
SELECT id, created_at FROM attempt;
COMMIT;
"""
        try:
            p_rows = db_sql(persist_sql)
        except Exception as exc:
            sys.stderr.write(f"practice: diagnostic opt-out persistence failed: {exc}\n")
            self._respond(500, {"error": "database persistence error"})
            return

        attempt_id = int(p_rows[0][0])
        created_at_val = str(p_rows[0][1])

        self._respond(200, {
            "ok": True,
            "attempt_id": attempt_id,
            "student_id": student_id,
            "diagnostic_id": diagnostic_id,
            "passed": False,
            "score_pct": 0.0,
            "route": "opt_out",
            "unlocked_units": baseline_units,
            "created_at": created_at_val,
        })

    def _handle_get_latest_digest(self, student_id: int) -> None:
        """S4.3: Retrieve the most recent generated weekly personalized digest for a student."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return

        digest_record = digests.get_latest_student_digest(student_id)
        if not digest_record:
            self._respond(200, {
                "student_id": student_id,
                "has_digest": False,
                "digest": None,
            })
            return

        self._respond(200, {
            "student_id": student_id,
            "has_digest": True,
            "digest": digest_record,
        })

    def _handle_get_pod_members(self, student_id: int) -> None:
        """S4.2: Retrieve student's current active pod details, Discord deep link, and peer list."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return

        detail = pods.get_student_pod_details(student_id)
        if not detail:
            self._respond(200, {
                "student_id": student_id,
                "has_pod": False,
                "pod": None,
            })
            return

        self._respond(200, {
            "student_id": student_id,
            "has_pod": True,
            "pod": detail,
        })

    def _handle_get_pod_posts(self, pod_id: int, week_number: int | None = None) -> None:
        """S4.2: Retrieve all submitted weekly accountability posts for a pod."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM pods WHERE id = %d);\nROLLBACK;\n" % pod_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "pod_not_found"})
            return

        posts_list = pods.get_pod_posts(pod_id, week_number)
        self._respond(200, {
            "pod_id": pod_id,
            "week_number": week_number,
            "posts": posts_list,
        })

    # ------------------------------------------------------------------
    # S4.4: Public Build Gallery Handlers
    # ------------------------------------------------------------------

    def _handle_get_gallery(self, query: dict[str, list[str]]) -> None:
        """S4.4: List public published gallery projects with optional unit/phase filters and pagination."""
        unit_id = (query.get("unit_id") or query.get("unit") or [None])[0]
        phase_raw = (query.get("phase") or [None])[0]
        phase = int(phase_raw) if phase_raw and phase_raw.isdigit() else None
        search = (query.get("search") or query.get("q") or [None])[0]
        limit_raw = (query.get("limit") or ["50"])[0]
        limit = int(limit_raw) if limit_raw.isdigit() else 50
        offset_raw = (query.get("offset") or ["0"])[0]
        offset = int(offset_raw) if offset_raw.isdigit() else 0

        res = gallery.list_gallery_projects(
            unit_id=unit_id,
            phase=phase,
            search=search,
            limit=limit,
            offset=offset,
        )
        self._respond(200, res)

    def _handle_get_gallery_project(self, project_id: int) -> None:
        """S4.4: Retrieve full details and verification proof for a single gallery project."""
        res = gallery.get_gallery_project(project_id)
        if not res:
            self._respond(404, {"error": "project_not_found", "message": f"Gallery project #{project_id} not found"})
            return
        self._respond(200, res)

    def _handle_get_student_gallery(self, student_id: int) -> None:
        """S4.4: Retrieve all gallery project entries for a student (published & unpublished)."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return
        projects = gallery.get_student_gallery_projects(student_id)
        self._respond(200, {
            "student_id": student_id,
            "projects": projects,
        })

    def _handle_get_submission_gallery(self, submission_id: int) -> None:
        """S4.4: Retrieve gallery project entry linked to a specific submission record."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM submissions WHERE id = %d);\nROLLBACK;\n" % submission_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "submission_not_found"})
            return
        proj = gallery.get_submission_gallery_project(submission_id)
        self._respond(200, {
            "submission_id": submission_id,
            "has_gallery_project": proj is not None,
            "project": proj,
        })

    def _handle_gallery_publish(self) -> None:
        """S4.4: Publish/showcase a verified passing project to the public build gallery."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        submission_id = payload.get("submission_id")
        title = payload.get("title")
        description = payload.get("description")
        repo_url = payload.get("repo_url")
        demo_url = payload.get("demo_url")
        walkthrough_video_url = payload.get("walkthrough_video_url")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(submission_id, int) or submission_id <= 0:
            self._respond(422, {"error": "submission_id (positive integer) is required"})
            return
        if not isinstance(title, str) or not title.strip():
            self._respond(422, {"error": "title_required", "message": "Project title is required"})
            return
        if not isinstance(description, str) or not description.strip():
            self._respond(422, {"error": "description_required", "message": "Project description is required"})
            return

        now_override = practice_now_override()

        try:
            res = gallery.publish_gallery_project(
                student_id=student_id,
                submission_id=submission_id,
                title=title,
                description=description,
                repo_url=repo_url,
                demo_url=demo_url,
                walkthrough_video_url=walkthrough_video_url,
                now_override=now_override,
            )
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "submission_ownership_mismatch", "message": "Submission does not belong to student"})
        except KeyError as exc:
            self._respond(404, {"error": "student_not_found", "message": str(exc)})
        except ValueError as exc:
            err_code = str(exc)
            if err_code == "submission_not_found":
                self._respond(404, {"error": "submission_not_found", "message": "Submission record not found"})
            elif err_code == "submission_not_eligible_for_gallery":
                self._respond(422, {"error": "submission_not_eligible_for_gallery", "message": "Only verified passing submissions can be published to the gallery"})
            else:
                self._respond(422, {"error": err_code})
        except Exception as exc:
            sys.stderr.write(f"practice: gallery publish error: {exc}\n")
            self._respond(500, {"error": "gallery_publish_error", "detail": str(exc)})

    def _handle_gallery_unpublish(self) -> None:
        """S4.4: Unpublish a gallery project, hiding it from the public listing."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        project_id = payload.get("project_id")
        unit_id = payload.get("unit_id")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if project_id is None and unit_id is None:
            self._respond(422, {"error": "project_id_or_unit_id_required", "message": "Either project_id or unit_id is required"})
            return
        if project_id is not None and not isinstance(project_id, int):
            self._respond(422, {"error": "project_id must be an integer"})
            return
        if unit_id is not None and not isinstance(unit_id, str):
            self._respond(422, {"error": "unit_id must be a string"})
            return

        now_override = practice_now_override()

        try:
            res = gallery.unpublish_gallery_project(
                student_id=student_id,
                project_id=project_id,
                unit_id=unit_id,
                now_override=now_override,
            )
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "project_ownership_mismatch", "message": "Gallery project belongs to a different student"})
        except KeyError:
            self._respond(404, {"error": "project_not_found", "message": "Gallery project not found"})
        except ValueError as exc:
            self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: gallery unpublish error: {exc}\n")
            self._respond(500, {"error": "gallery_unpublish_error", "detail": str(exc)})

    def _handle_pod_assign(self) -> None:
        """S4.2: Assign student to a pod for their cohort week (idempotent, 6-10 capacity)."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        cohort_week = payload.get("cohort_week")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if cohort_week is not None and not isinstance(cohort_week, str):
            self._respond(422, {"error": "cohort_week must be a string (e.g. 2026-W35)"})
            return

        now_override = practice_now_override()

        try:
            res = pods.assign_student_to_pod(
                student_id=student_id,
                cohort_week=cohort_week,
                now_override=now_override,
            )
            self._respond(200, {
                "ok": True,
                "student_id": student_id,
                **res,
            })
        except ValueError as exc:
            if str(exc) == "student_not_found":
                self._respond(404, {"error": "student_not_found"})
            else:
                self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: pod assignment error: {exc}\n")
            self._respond(500, {"error": "pod_assignment_error", "detail": str(exc)})

    def _handle_pod_post_submit(self) -> None:
        """S4.2: Submit weekly accountability check-in post with 3 mandatory pillars."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        pod_id = payload.get("pod_id")
        week_number = payload.get("week_number")
        shipped_text = payload.get("shipped_text")
        broke_text = payload.get("broke_text")
        next_text = payload.get("next_text")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(pod_id, int) or pod_id <= 0:
            self._respond(422, {"error": "pod_id (positive integer) is required"})
            return
        if not isinstance(week_number, int) or week_number < 1:
            self._respond(422, {"error": "week_number (integer >= 1) is required"})
            return
        if not isinstance(shipped_text, str) or not shipped_text.strip():
            self._respond(422, {"error": "shipped_text_required", "message": "What shipped text is required"})
            return
        if not isinstance(broke_text, str) or not broke_text.strip():
            self._respond(422, {"error": "broke_text_required", "message": "What broke text is required"})
            return
        if not isinstance(next_text, str) or not next_text.strip():
            self._respond(422, {"error": "next_text_required", "message": "What's next text is required"})
            return

        now_override = practice_now_override()

        try:
            res = pods.submit_pod_post(
                student_id=student_id,
                pod_id=pod_id,
                week_number=week_number,
                shipped_text=shipped_text,
                broke_text=broke_text,
                next_text=next_text,
                now_override=now_override,
            )
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "not_pod_member", "message": "Student is not an active member of this pod"})
        except KeyError:
            self._respond(409, {"error": "post_already_submitted_for_week", "message": f"Weekly post already submitted for week {week_number}"})
        except ValueError as exc:
            self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: pod post submission error: {exc}\n")
            self._respond(500, {"error": "pod_post_error", "detail": str(exc)})

    def _handle_diagnostic_evaluate(self) -> None:
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        diagnostic_id = payload.get("diagnostic_id") or "placement-phase-1"
        answers = payload.get("answers")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(answers, dict):
            self._respond(422, {"error": "answers object is required"})
            return

        spec = get_diagnostic_spec(diagnostic_id)
        if not spec:
            self._respond(404, {"error": "diagnostic_spec_not_found"})
            return

        # 1. Verify student exists
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return

        # 2. Score answers deterministically
        evaluation = evaluate_diagnostic(spec, answers)
        passed = evaluation["passed"]
        score_pct = evaluation["score_pct"]
        route = evaluation["route"]
        points_earned = evaluation["points_earned"]
        points_possible = evaluation["points_possible"]
        unlocked_units = evaluation["unlocked_units"]
        breakdown = evaluation["breakdown"]

        now_override = practice_now_override()
        created_at_sql = sql_str(now_override.isoformat()) if now_override is not None else "now()"

        # 3. Atomic persistence: diagnostic_attempts + spine events + unlocked_units
        units_values = ", ".join(sql_str(u) for u in unlocked_units)
        gate_id = "diagnostic-pass-skip" if passed else "diagnostic-baseline"
        answers_json_str = sql_str(json.dumps(answers))
        breakdown_json_str = sql_str(json.dumps(breakdown))
        unlocked_json_str = sql_str(json.dumps(unlocked_units))
        passed_str = "true" if passed else "false"

        persist_sql = f"""BEGIN;
WITH attempt AS (
    INSERT INTO diagnostic_attempts (
        student_id, diagnostic_id, passed, score_pct, points_earned, points_possible,
        route, answers_json, breakdown_json, created_at
    ) VALUES (
        {student_id}, {sql_str(diagnostic_id)}, {passed_str}, {sql_str(str(score_pct))}, {points_earned}, {points_possible},
        {sql_str(route)}, {answers_json_str}::jsonb, {breakdown_json_str}::jsonb, {created_at_sql}
    )
    RETURNING id, student_id, diagnostic_id, passed, score_pct, route, created_at
), ins AS (
    INSERT INTO unlocked_units (student_id, unit_id, gate_id, unlocked_at, source_event_seq)
    SELECT {student_id}, u, {sql_str(gate_id)}, {created_at_sql}, (SELECT id FROM attempt)
    FROM unnest(ARRAY[{units_values}]::text[]) u
    ON CONFLICT (student_id, unit_id) DO NOTHING
    RETURNING student_id, unit_id, unlocked_at
), ev1 AS (
    INSERT INTO events (type, payload)
    SELECT 'diagnostic.completed',
           jsonb_build_object(
               'attempt_id', id,
               'student_id', student_id,
               'diagnostic_id', diagnostic_id,
               'passed', passed,
               'score_pct', score_pct,
               'points_earned', {points_earned},
               'points_possible', {points_possible}
           )
    FROM attempt
    RETURNING id
), ev2 AS (
    INSERT INTO events (type, payload)
    SELECT 'diagnostic.placed',
           jsonb_build_object(
               'attempt_id', id,
               'student_id', student_id,
               'diagnostic_id', diagnostic_id,
               'passed', passed,
               'score_pct', score_pct,
               'route', route,
               'unlocked_units', {unlocked_json_str}::jsonb
           )
    FROM attempt
    RETURNING id
)
SELECT id, created_at FROM attempt;
COMMIT;
"""
        try:
            p_rows = db_sql(persist_sql)
        except Exception as exc:
            sys.stderr.write(f"practice: diagnostic evaluate persistence failed: {exc}\n")
            self._respond(500, {"error": "database persistence error"})
            return

        attempt_id = int(p_rows[0][0])
        created_at_val = str(p_rows[0][1])

        self._respond(200, {
            "ok": True,
            "attempt_id": attempt_id,
            "student_id": student_id,
            "diagnostic_id": diagnostic_id,
            "passed": passed,
            "score_pct": score_pct,
            "points_earned": points_earned,
            "points_possible": points_possible,
            "route": route,
            "unlocked_units": unlocked_units,
            "breakdown": breakdown,
            "created_at": created_at_val,
        })

    # ------------------------------------------------------------------
    # S4.5: Simulation Handlers (Discovery-call & Reviewer engine)
    # ------------------------------------------------------------------

    def _handle_simulation_start(self) -> None:
        """S4.5: Start a new simulation session for (student_id, persona_id)."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        persona_id = payload.get("persona_id") or "discovery-call"

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(persona_id, str) or not persona_id.strip():
            self._respond(422, {"error": "persona_id (string) is required"})
            return

        now_override = practice_now_override()

        try:
            res = simulation.start_simulation_session(
                student_id=student_id,
                persona_id=persona_id.strip(),
                now_override=now_override,
            )
            self._respond(200, res)
        except KeyError as exc:
            err_msg = str(exc)
            if "student_not_found" in err_msg:
                self._respond(404, {"error": "student_not_found", "message": "Student not found"})
            elif "persona_not_found" in err_msg:
                self._respond(404, {"error": "persona_not_found", "message": f"Persona {persona_id} not found"})
            else:
                self._respond(404, {"error": err_msg})
        except ValueError as exc:
            self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: simulation start error: {exc}\n")
            self._respond(500, {"error": "simulation_start_error", "detail": str(exc)})

    def _handle_simulation_turn(self) -> None:
        """S4.5: Execute a dialogue turn in an active simulation session."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        simulation_id = payload.get("simulation_id")
        student_id = payload.get("student_id")
        message = payload.get("message")

        if not isinstance(simulation_id, int) or simulation_id <= 0:
            self._respond(422, {"error": "simulation_id (positive integer) is required"})
            return
        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(message, str) or not message.strip():
            self._respond(422, {"error": "message_required", "message": "Message content is required"})
            return

        now_override = practice_now_override()

        try:
            res = simulation.execute_simulation_turn(
                simulation_id=simulation_id,
                student_id=student_id,
                message=message,
                now_override=now_override,
            )
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "simulation_ownership_mismatch", "message": "Simulation belongs to another student"})
        except KeyError:
            self._respond(404, {"error": "simulation_not_found", "message": "Simulation session not found"})
        except ValueError as exc:
            self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: simulation turn error: {exc}\n")
            self._respond(500, {"error": "simulation_turn_error", "detail": str(exc)})

    def _handle_simulation_conclude(self) -> None:
        """S4.5: Conclude simulation session, trigger evaluation judge, persist verdict."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        simulation_id = payload.get("simulation_id")
        student_id = payload.get("student_id")

        if not isinstance(simulation_id, int) or simulation_id <= 0:
            self._respond(422, {"error": "simulation_id (positive integer) is required"})
            return
        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return

        now_override = practice_now_override()

        try:
            res = simulation.conclude_and_score_simulation(
                simulation_id=simulation_id,
                student_id=student_id,
                now_override=now_override,
            )
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "simulation_ownership_mismatch", "message": "Simulation belongs to another student"})
        except KeyError as exc:
            self._respond(404, {"error": "simulation_not_found", "message": str(exc)})
        except ValueError as exc:
            self._respond(422, {"error": str(exc)})
        except Exception as exc:
            sys.stderr.write(f"practice: simulation conclude error: {exc}\n")
            self._respond(500, {"error": "simulation_conclude_error", "detail": str(exc)})

    def _handle_get_simulation(self, simulation_id: int, query: dict[str, list[str]]) -> None:
        """S4.5: Retrieve simulation session transcript and verdict."""
        sid_raw = (query.get("student_id") or [None])[0]
        requesting_student_id = int(sid_raw) if sid_raw and sid_raw.isdigit() else None
        try:
            res = simulation.get_simulation_detail(simulation_id, requesting_student_id=requesting_student_id)
            self._respond(200, res)
        except PermissionError:
            self._respond(403, {"error": "simulation_ownership_mismatch", "message": "Simulation belongs to another student"})
        except KeyError:
            self._respond(404, {"error": "simulation_not_found", "message": "Simulation not found"})
        except Exception as exc:
            sys.stderr.write(f"practice: get simulation error: {exc}\n")
            self._respond(500, {"error": "simulation_detail_error", "detail": str(exc)})

    def _handle_get_student_simulations(self, student_id: int) -> None:
        """S4.5: Retrieve all simulations for a student."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return
        sims = simulation.list_student_simulations(student_id)
        self._respond(200, {
            "student_id": student_id,
            "simulations": sims,
        })

    def _handle_get_student_defenses(self, student_id: int) -> None:
        """S4.6: Retrieve skeptical reviewer defense status for a student."""
        chk = db_sql("BEGIN;\nSELECT EXISTS (SELECT 1 FROM students WHERE id = %d);\nROLLBACK;\n" % student_id)
        if not chk or chk[0][0] != "t":
            self._respond(404, {"error": "student_not_found"})
            return
        defenses = simulation.get_student_defenses(student_id)
        self._respond(200, defenses)

    # ------------------------------------------------------------------
    # S4.7: Analytics & Drop-off Handlers
    # ------------------------------------------------------------------

    def _handle_get_analytics_summary(self) -> None:
        """S4.7: High-level operations KPIs (students, retention, pod compliance, graduation)."""
        now_override = practice_now_override()
        try:
            res = analytics.compute_summary(now_override=now_override)
            self._respond(200, res)
        except Exception as exc:
            sys.stderr.write(f"practice: analytics summary error: {exc}\n")
            self._respond(500, {"error": "analytics_summary_error", "detail": str(exc)})

    def _handle_get_analytics_funnel(self) -> None:
        """S4.7: Curriculum macro funnel stage conversions."""
        now_override = practice_now_override()
        try:
            res = analytics.compute_macro_funnel(now_override=now_override)
            self._respond(200, res)
        except Exception as exc:
            sys.stderr.write(f"practice: analytics funnel error: {exc}\n")
            self._respond(500, {"error": "analytics_funnel_error", "detail": str(exc)})

    def _handle_get_analytics_dropoff(self, query: dict[str, list[str]]) -> None:
        """S4.7: Per-unit drop-off and friction breakdown with optional phase filter."""
        phase_raw = (query.get("phase") or [None])[0]
        phase = int(phase_raw) if phase_raw and phase_raw.isdigit() else None
        now_override = practice_now_override()
        try:
            res = analytics.compute_dropoff_breakdown(phase=phase, now_override=now_override)
            self._respond(200, res)
        except Exception as exc:
            sys.stderr.write(f"practice: analytics dropoff error: {exc}\n")
            self._respond(500, {"error": "analytics_dropoff_error", "detail": str(exc)})

    def _handle_get_analytics_unit(self, unit_id: str) -> None:
        """S4.7: Detailed friction drill-down for a single unit."""
        now_override = practice_now_override()
        try:
            res = analytics.compute_unit_detail(unit_id=unit_id, now_override=now_override)
            self._respond(200, res)
        except Exception as exc:
            sys.stderr.write(f"practice: analytics unit detail error: {exc}\n")
            self._respond(500, {"error": "analytics_unit_detail_error", "detail": str(exc)})


    def _handle_get_manifest(self, unit_id: str) -> None:
        if not UNIT_RE.match(unit_id):
            self._respond(400, {"error": "bad unit id"})
            return
        manifest = get_unit_practice_manifest(unit_id)
        if not manifest:
            self._respond(404, {"error": "completion problem not found for unit"})
            return
        resp_obj = {
            "unit_id": manifest["unit_id"],
            "kind": manifest.get("kind", "code"),
            "base_rel": manifest["base_rel"],
            "readme_markdown": manifest["readme_markdown"],
            "base_files": manifest["base_files"],
            "editable_files": manifest["editable_files"],
            "checks": manifest["checks"],
        }
        if manifest.get("kind") == "conceptual":
            resp_obj["prompt"] = manifest.get("prompt", "")
            resp_obj["instructions"] = manifest.get("instructions", "")
            resp_obj["model_answer_markdown"] = manifest.get("model_answer_markdown", "")
        self._respond(200, resp_obj)

    def _handle_get_attempts(self, student_id: int, unit_id: str) -> None:
        sql = """BEGIN;
SELECT id, student_id, unit_id, passed, pass_count, total_checks, results_json::text, created_at
FROM practice_attempts
WHERE student_id = %d AND unit_id = %s
ORDER BY id DESC
LIMIT 50;
ROLLBACK;
""" % (student_id, sql_str(unit_id))
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        attempts = []
        for r in rows:
            attempts.append({
                "id": int(r[0]),
                "student_id": int(r[1]),
                "unit_id": r[2],
                "passed": r[3] == "t" or r[3] is True,
                "pass_count": int(r[4]),
                "total_checks": int(r[5]),
                "checks": json.loads(r[6]),
                "created_at": str(r[7]),
            })
        self._respond(200, {"attempts": attempts})

    def _handle_get_retrieval_seeds(self, unit_id: str) -> None:
        if not UNIT_RE.match(unit_id):
            self._respond(400, {"error": "bad unit id"})
            return
        seeds = get_unit_retrieval_seeds(unit_id)
        if not seeds:
            self._respond(404, {"error": "retrieval seeds not found for unit"})
            return
        seed_objs = [{"index": idx, "prompt": prompt} for idx, prompt in enumerate(seeds)]
        self._respond(200, {
            "unit_id": unit_id,
            "seeds": seed_objs,
        })

    def _handle_get_retrieval_attempts(self, student_id: int, unit_id: str) -> None:
        sql = """BEGIN;
SELECT id, student_id, unit_id, seed_index, seed_prompt, student_answer,
       passed, feedback, evidence, tokens_charged, verdict_json::text, created_at
FROM retrieval_attempts
WHERE student_id = %d AND unit_id = %s
ORDER BY id DESC
LIMIT 50;
ROLLBACK;
""" % (student_id, sql_str(unit_id))
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        attempts = []
        for r in rows:
            attempts.append({
                "id": int(r[0]),
                "student_id": int(r[1]),
                "unit_id": r[2],
                "seed_index": int(r[3]),
                "seed_prompt": r[4],
                "student_answer": r[5],
                "passed": r[6] == "t" or r[6] is True,
                "feedback": r[7],
                "evidence": r[8],
                "tokens_charged": int(r[9]),
                "verdict_json": json.loads(r[10]),
                "created_at": str(r[11]),
            })
        self._respond(200, {"attempts": attempts})

    def _handle_get_recheck_schedule(self, student_id: int, unit_id: str | None) -> None:
        """S3.3: derive the spaced re-check schedule from retrieval_attempts.

        Read-only. Only units with an ACTIVE enrollment contribute (attempts
        made before an enrollment lapsed cannot resurrect a schedule). Each
        seed with at least one pass appears exactly once with its derived
        state; the fold rules live in fold_seed_schedule().
        """
        if unit_id is not None:
            sql = """BEGIN;
SELECT seed_index, seed_prompt, passed, created_at::text
FROM retrieval_attempts
WHERE student_id = %d AND unit_id = %s
  AND EXISTS (
      SELECT 1 FROM enrollments
      WHERE student_id = %d AND unit_id = %s AND status = 'active'
  )
ORDER BY seed_index ASC, created_at ASC, id ASC;
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id, sql_str(unit_id))
        else:
            sql = """BEGIN;
SELECT unit_id, seed_index, seed_prompt, passed, created_at::text
FROM retrieval_attempts
WHERE student_id = %d
  AND EXISTS (
      SELECT 1 FROM enrollments e
      WHERE e.student_id = %d AND e.unit_id = retrieval_attempts.unit_id AND e.status = 'active'
  )
ORDER BY unit_id ASC, seed_index ASC, created_at ASC, id ASC;
ROLLBACK;
""" % (student_id, student_id)
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        now = practice_now()
        grouped: dict[tuple[str, int], dict[str, Any]] = {}
        for r in rows:
            if unit_id is not None:
                uid, seed_index, seed_prompt = unit_id, int(r[0]), r[1]
                passed_raw, created_raw = r[2], r[3]
            else:
                uid, seed_index, seed_prompt = r[0], int(r[1]), r[2]
                passed_raw, created_raw = r[3], r[4]
            passed = passed_raw == "t" or passed_raw is True
            created_at = datetime.fromisoformat(created_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            key = (uid, seed_index)
            bucket = grouped.setdefault(key, {"seed_prompt": seed_prompt, "attempts": []})
            bucket["attempts"].append((passed, created_at))

        seeds_out = []
        due_count = 0
        for (uid, seed_index) in sorted(grouped.keys()):
            bucket = grouped[(uid, seed_index)]
            state = fold_seed_schedule(bucket["attempts"], now)
            if state["stage"] == 0:
                continue  # never passed: no schedule exists for this seed
            mastery = derive_seed_mastery(bucket["attempts"], state, now)
            entry = {
                "unit_id": uid,
                "seed_index": seed_index,
                "seed_prompt": bucket["seed_prompt"],
                "stage": state["stage"],
                "status": state["status"],
                "mastery": mastery,
                "last_pass_at": state["last_pass_at"].isoformat() if state["last_pass_at"] else None,
                "due_at": state["due_at"].isoformat() if state["due_at"] else None,
            }
            if state["status"] == "due":
                due_count += 1
            seeds_out.append(entry)

        self._respond(200, {
            "student_id": student_id,
            "now": now.isoformat(),
            "due_count": due_count,
            "seeds": seeds_out,
        })

    def _handle_get_review_queue(self, student_id: int) -> None:
        """U5: return due review items across ALL units, interleaved, unlabeled by unit."""
        sql = """BEGIN;
SELECT unit_id, seed_index, seed_prompt, passed, created_at::text
FROM retrieval_attempts
WHERE student_id = %d
  AND EXISTS (
      SELECT 1 FROM enrollments e
      WHERE e.student_id = %d AND e.unit_id = retrieval_attempts.unit_id AND e.status = 'active'
  )
ORDER BY unit_id ASC, seed_index ASC, created_at ASC, id ASC;
ROLLBACK;
""" % (student_id, student_id)
        try:
            rows = db_sql(sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        now = practice_now()
        grouped: dict[tuple[str, int], dict[str, Any]] = {}
        for r in rows:
            uid, seed_index, seed_prompt = r[0], int(r[1]), r[2]
            passed_raw, created_raw = r[3], r[4]
            passed = passed_raw == "t" or passed_raw is True
            created_at = datetime.fromisoformat(created_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            key = (uid, seed_index)
            bucket = grouped.setdefault(key, {"seed_prompt": seed_prompt, "attempts": []})
            bucket["attempts"].append((passed, created_at))

        due_items: list[dict[str, Any]] = []
        for (uid, seed_index) in sorted(grouped.keys()):
            bucket = grouped[(uid, seed_index)]
            state = fold_seed_schedule(bucket["attempts"], now)
            if state["status"] == "due":
                mastery = derive_seed_mastery(bucket["attempts"], state, now)
                due_items.append({
                    "review_id": f"{uid}:{seed_index}",
                    "unit_id": uid,
                    "seed_index": seed_index,
                    "seed_prompt": bucket["seed_prompt"],
                    "mastery": mastery,
                    "stage": state["stage"],
                    "due_at": state["due_at"].isoformat() if state["due_at"] else None,
                })

        # Interleave across units deterministically (round-robin across units)
        by_unit: dict[str, list[dict[str, Any]]] = {}
        for item in due_items:
            by_unit.setdefault(item["unit_id"], []).append(item)

        interleaved: list[dict[str, Any]] = []
        unit_keys = sorted(by_unit.keys())
        idx = 0
        while any(by_unit.values()):
            u = unit_keys[idx % len(unit_keys)]
            if by_unit[u]:
                interleaved.append(by_unit[u].pop(0))
            idx += 1

        self._respond(200, {
            "student_id": student_id,
            "now": now.isoformat(),
            "due_count": len(interleaved),
            "items": interleaved,
        })

    def _handle_get_practice_route(self, student_id: int, unit_id: str) -> None:
        """S3.4: compute adaptive practice route derived from attempt history."""
        if not UNIT_RE.match(unit_id):
            self._respond(400, {"error": "bad unit id"})
            return

        rules = get_unit_routing_rules(unit_id)
        if not rules:
            self._respond(404, {
                "error": "routing_rules_not_found",
                "message": f"No routing rules found for unit {unit_id}",
            })
            return

        seeds = get_unit_retrieval_seeds(unit_id)

        # 1. Check student existence and active enrollment in a single read transaction
        gate_sql = """BEGIN;
SELECT EXISTS (
    SELECT 1 FROM enrollments
    WHERE student_id = %d AND unit_id = %s AND status = 'active'
), EXISTS (
    SELECT 1 FROM students WHERE id = %d
);
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id)
        try:
            gate_rows = db_sql(gate_sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        is_enrolled = gate_rows[0][0] == "t" or gate_rows[0][0] is True
        student_exists = gate_rows[0][1] == "t" or gate_rows[0][1] is True

        if not student_exists:
            self._respond(404, {"error": "student_not_found"})
            return

        if not is_enrolled:
            route_data = derive_unit_practice_route(
                student_id=student_id,
                unit_id=unit_id,
                is_enrolled=False,
                retrieval_attempts=[],
                practice_attempts=[],
                seeds=seeds,
                rules=rules,
            )
            self._respond(200, route_data)
            return

        # 2. Query attempts history (read-only, wrapped in BEGIN/ROLLBACK)
        attempts_sql = """BEGIN;
SELECT 'retrieval' AS kind, id, seed_index, (passed = 't')::text, 0 AS pass_count, 0 AS total_checks, created_at::text
FROM retrieval_attempts
WHERE student_id = %d AND unit_id = %s
UNION ALL
SELECT 'practice' AS kind, id, -1 AS seed_index, (passed = 't')::text, pass_count, total_checks, created_at::text
FROM practice_attempts
WHERE student_id = %d AND unit_id = %s
ORDER BY 1, 2 ASC;
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id, sql_str(unit_id))
        try:
            rows = db_sql(attempts_sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        retrieval_attempts: list[dict[str, Any]] = []
        practice_attempts: list[dict[str, Any]] = []

        for r in rows:
            kind, att_id, s_idx, passed_str, p_count, tot_checks, created_at = r
            passed = (passed_str == "true" or passed_str == "t" or passed_str is True)
            if kind == "retrieval":
                retrieval_attempts.append({
                    "id": int(att_id),
                    "seed_index": int(s_idx),
                    "passed": passed,
                    "created_at": created_at,
                })
            else:
                practice_attempts.append({
                    "id": int(att_id),
                    "passed": passed,
                    "pass_count": int(p_count),
                    "total_checks": int(tot_checks),
                    "created_at": created_at,
                })

        route_data = derive_unit_practice_route(
            student_id=student_id,
            unit_id=unit_id,
            is_enrolled=True,
            retrieval_attempts=retrieval_attempts,
            practice_attempts=practice_attempts,
            seeds=seeds,
            rules=rules,
        )
        self._respond(200, route_data)

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------

    def do_POST(self) -> None:
        if not self._app_authorized():
            self._read_body()
            self._bad_token()
            return

        parsed = urllib.parse.urlsplit(self.path)

        # Simulation sessions & dialogue turns (S4.5)
        if parsed.path in ("/simulation/start", "/simulations/start"):
            self._handle_simulation_start()
            return
        if parsed.path in ("/simulation/turn", "/simulations/turn"):
            self._handle_simulation_turn()
            return
        if parsed.path in ("/simulation/conclude", "/simulations/conclude"):
            self._handle_simulation_conclude()
            return

        # Gallery publishing & unpublishing (S4.4)
        if parsed.path in ("/gallery/publish", "/gallery/showcase"):
            self._handle_gallery_publish()
            return
        if parsed.path in ("/gallery/unpublish", "/gallery/hide"):
            self._handle_gallery_unpublish()
            return

        # Pod management & weekly posts (S4.2)
        if parsed.path in ("/pod/assign", "/pods/assign"):
            self._handle_pod_assign()
            return
        if parsed.path in ("/pod/posts", "/pod/post", "/pods/posts"):
            self._handle_pod_post_submit()
            return

        # Diagnostic evaluation & opt-out (S4.1)
        if parsed.path in ("/diagnostic/evaluate", "/diagnostic/attempt"):
            self._handle_diagnostic_evaluate()
            return
        if parsed.path in ("/diagnostic/opt-out", "/diagnostic/bypass"):
            self._handle_diagnostic_opt_out()
            return

        # Concierge ask (S3.5)
        if parsed.path in ("/concierge/ask", "/concierge/submit"):
            self._handle_concierge_ask()
            return
        m_cask = re.match(r"^/units/(\d+\.\d+(?:\.\d+)?)/concierge/ask$", parsed.path)
        if m_cask:
            self._handle_concierge_ask(unit_id_override=m_cask.group(1))
            return

        # Retrieval drill attempt
        if parsed.path in ("/practice/retrieval/attempt", "/practice/retrieval/submit"):
            self._handle_retrieval_attempt()
            return
        m_ratt = re.match(r"^/units/(\d+\.\d+(?:\.\d+)?)/practice/retrieval/attempt$", parsed.path)
        if m_ratt:
            self._handle_retrieval_attempt(unit_id_override=m_ratt.group(1))
            return

        # Completion problem attempt
        if parsed.path in ("/practice/attempt", "/practice/submit"):
            self._handle_attempt()
            return
        m_att = re.match(r"^/units/(\d+\.\d+(?:\.\d+)?)/practice/attempt$", parsed.path)
        if m_att:
            self._handle_attempt(unit_id_override=m_att.group(1))
            return

        # Explain-it-back step evaluation (U7)
        if parsed.path in ("/practice/explain/evaluate", "/practice/explain/submit"):
            self._handle_explain_evaluate()
            return

        self._respond(404, {"error": "not found"})

    def _handle_explain_evaluate(self) -> None:
        """U7: judge the student's 2-3 sentence explain-it-back response."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        unit_id = str(payload.get("unit_id", "")).strip()
        explanation = str(payload.get("explanation", "")).strip()

        if not student_id or not str(student_id).isdigit():
            self._respond(400, {"error": "student_id (int) required"})
            return
        if not UNIT_RE.match(unit_id):
            self._respond(400, {"error": "valid unit_id required"})
            return
        if not explanation:
            self._respond(400, {"error": "explanation required"})
            return

        words = [w for w in explanation.split() if w]
        if len(words) < 8:
            self._respond(200, {
                "ok": True,
                "passed": False,
                "feedback": "Your explanation is too brief. In 2 to 3 sentences, describe what you changed and why downstream consumers depend on that invariant.",
                "score": 30,
            })
            return

        text_lower = explanation.lower()
        key_signals = [
            "schema", "model", "validat", "boundar", "pydantic",
            "type", "parse", "enforc", "downstream", "contract",
            "field", "fail", "safe", "handl", "shape", "error"
        ]
        matches = sum(1 for sig in key_signals if sig in text_lower)

        if matches >= 2:
            feedback = (
                "Accurate and clear explanation. You correctly identified the boundary invariant "
                "and how typed schema enforcement prevents malformed inputs from breaking downstream services."
            )
            passed = True
            score = 100
        else:
            feedback = (
                "You described part of the solution, but clarify what structural guarantee "
                "your code enforces at the boundary and why downstream code relies on it."
            )
            passed = False
            score = 65

        self._respond(200, {
            "ok": True,
            "passed": passed,
            "feedback": feedback,
            "score": score,
        })

    def _handle_attempt(self, unit_id_override: str | None = None) -> None:
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        unit_id = unit_id_override or payload.get("unit_id")
        files = payload.get("files")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(unit_id, str) or not UNIT_RE.match(unit_id):
            self._respond(422, {"error": "unit_id (x.y.z) is required"})
            return

        # 1. Load manifest and verify unit
        manifest = get_unit_practice_manifest(unit_id)
        if not manifest:
            self._respond(404, {"error": "completion problem not found for unit"})
            return

        is_conceptual = manifest.get("kind") == "conceptual"
        if not is_conceptual and (not isinstance(files, dict) or not files):
            self._respond(422, {"error": "files object with submitted files is required"})
            return

        # 2. Strict Whitelist & Payload Validation
        submitted_files_clean: dict[str, str] = {}
        conceptual_answer = ""
        if is_conceptual:
            # For conceptual units, answer may be passed in payload["answer"] or files["answer"] / files["response"]
            if isinstance(payload.get("answer"), str) and payload["answer"].strip():
                conceptual_answer = payload["answer"].strip()
            elif isinstance(files, dict):
                for k, v in files.items():
                    if isinstance(v, str) and v.strip():
                        conceptual_answer = v.strip()
                        break
            if not conceptual_answer:
                self._respond(422, {"error": "answer_required", "message": "Conceptual response text is required"})
                return
            if len(conceptual_answer.encode("utf-8")) > MAX_FILE_BYTES:
                self._respond(400, {"error": "answer_too_large"})
                return
            if "\0" in conceptual_answer:
                self._respond(400, {"error": "binary_content_rejected"})
                return
            submitted_files_clean["answer.md"] = conceptual_answer
        else:
            editable_set = set(manifest["editable_files"])
            for fname, content in files.items():
                if not isinstance(fname, str) or not FILENAME_RE.match(fname) or len(fname) > MAX_FILENAME_LEN:
                    self._respond(400, {"error": "invalid_filename", "filename": str(fname)})
                    return
                if fname not in editable_set:
                    self._respond(400, {"error": "file_not_editable", "filename": fname, "editable_files": manifest["editable_files"]})
                    return
                if not isinstance(content, str):
                    self._respond(400, {"error": "file_content_must_be_string", "filename": fname})
                    return
                if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                    self._respond(400, {"error": "file_too_large", "filename": fname})
                    return
                if "\0" in content:
                    self._respond(400, {"error": "binary_content_rejected", "filename": fname})
                    return
                submitted_files_clean[fname] = content

        # 3. Enrollment Gate Authorization
        gate_sql = """BEGIN;
SELECT EXISTS (
    SELECT 1 FROM enrollments
    WHERE student_id = %d AND unit_id = %s AND status = 'active'
), EXISTS (
    SELECT 1 FROM students WHERE id = %d
);
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id)
        try:
            gate_rows = db_sql(gate_sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        is_enrolled = gate_rows[0][0] == "t" or gate_rows[0][0] is True
        student_exists = gate_rows[0][1] == "t" or gate_rows[0][1] is True

        if not student_exists:
            self._respond(404, {"error": "student_not_found"})
            return
        if not is_enrolled:
            self._respond(403, {"error": "not_enrolled", "message": f"Active enrollment required for unit {unit_id}"})
            return

        if is_conceptual:
            # 4/5. Conceptual grading via LLM Judge against rubric
            try:
                verdict_res, tokens_charged = grade_conceptual_completion_answer(
                    student_id=student_id,
                    unit_id=unit_id,
                    prompt=manifest.get("prompt", ""),
                    instructions=manifest.get("instructions", ""),
                    student_answer=conceptual_answer,
                )
            except BudgetExceeded as exc:
                self._respond(429, {"error": "budget_exceeded", "message": str(exc)})
                return
            except UpstreamError as exc:
                self._respond(502, {"error": "upstream_error", "message": str(exc)})
                return
            except MalformedJudgeError as exc:
                self._respond(502, {"error": "malformed_judge", "message": str(exc)})
                return
            except RubricError as exc:
                self._respond(500, {"error": "rubric_load_failed", "message": str(exc)})
                return

            # One check result per rubric criterion; the overall below is the
            # platform's pass_rule computation, never the model's own.
            c_passed = verdict_res.get("overall") == "pass"
            rationale = str(verdict_res.get("feedback", ""))
            check_results = [
                {
                    "id": crit["id"],
                    "type": "llm-judge",
                    "status": "pass" if crit["verdict"] == "pass" else "fail",
                    "note": str(crit.get("evidence", "")) or rationale,
                    "evidence": crit["evidence"],
                    "wall_s": None,
                    "exit_code": 0 if crit["verdict"] == "pass" else 1,
                    "container_status": "judge_graded",
                    "output_tail": f"Criterion {crit['id']}: {crit['verdict']}\nEvidence: {crit['evidence']}\nRationale: {rationale}",
                }
                for crit in verdict_res.get("criteria", [])
            ]
        else:
            # 4. Stage problem base + student file overrides
            staging_parent = Path(tempfile.mkdtemp(prefix="keel-practice-"))
            staging_sub = staging_parent / "submission"
            target_dir = staging_sub / manifest["base_rel"].rstrip("/")

            try:
                shutil.copytree(manifest["base_dir"], target_dir)
                for fname, content in submitted_files_clean.items():
                    (target_dir / fname).write_text(content, encoding="utf-8")

                # 5. Execute sandbox Layer-1 checks
                checks_data = yaml.safe_load(manifest["checks_path"].read_text(encoding="utf-8"))
                if not isinstance(checks_data, list) or not checks_data:
                    self._respond(500, {"error": "empty checks definition"})
                    return

                timeout_s = float(os.environ.get("KEEL_PRACTICE_TIMEOUT_S", DEFAULT_TIMEOUT_S))
                check_results = []
                for check in checks_data:
                    res = layer1.run_check_container(check, staging_sub, timeout_s)
                    check_results.append(res)

            except Exception as exc:
                sys.stderr.write(f"practice: staging/sandbox failure: {exc}\n")
                self._respond(502, {"error": "sandbox_execution_error", "detail": str(exc)})
                return
            finally:
                layer1.cleanup_staging(staging_parent)

        passed = all(r.get("status") == "pass" for r in check_results)
        if is_conceptual:
            # Platform-computed overall per the rubric pass_rule — never the model's.
            passed = c_passed
        pass_count = sum(1 for r in check_results if r.get("status") == "pass")
        total_checks = len(check_results)

        # 6. Atomic Persistence
        results_json_str = json.dumps(check_results)
        submitted_meta = json.dumps({f: len(c) for f, c in submitted_files_clean.items()})

        # Conceptual passes carry the unit's grade: emit a verdict.issued event
        # (the gate engine's only pass signal) alongside the attempt row, in the
        # same transaction. Code units keep practice.attempt_graded only; their
        # real verdict comes from the repo-push worker.
        verdict_ev = ""
        if is_conceptual and passed:
            verdict_payload = json.dumps({
                "student_id": student_id,
                "unit_id": unit_id,
                "overall": "pass",
                "source": "practice_conceptual",
            })
            verdict_ev = f""",
vev AS (
    INSERT INTO events (type, payload)
    SELECT 'verdict.issued',
           {sql_str(verdict_payload)}::jsonb
    WHERE NOT EXISTS (
        SELECT 1 FROM events
        WHERE type = 'verdict.issued'
          AND payload->>'student_id' = {sql_str(str(student_id))}
          AND payload->>'unit_id' = {sql_str(unit_id)}
          AND payload->>'overall' = 'pass'
    )
    RETURNING id
)"""

        persist_sql = f"""BEGIN;
WITH att AS (
    INSERT INTO practice_attempts (
        student_id, unit_id, passed, pass_count, total_checks, results_json, submitted_files
    ) VALUES (
        %d, %s, %s, %d, %d, %s::jsonb, %s::jsonb
    )
    RETURNING id, student_id, unit_id, passed, pass_count, total_checks, created_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'practice.attempt_graded',
           jsonb_build_object(
               'attempt_id', id,
               'student_id', student_id,
               'unit_id', unit_id::text,
               'passed', passed,
               'pass_count', pass_count,
               'total_checks', total_checks
           )
    FROM att
    RETURNING id
){verdict_ev}
SELECT id, created_at FROM att;
COMMIT;
""" % (
            student_id,
            sql_str(unit_id),
            "true" if passed else "false",
            pass_count,
            total_checks,
            sql_str(results_json_str),
            sql_str(submitted_meta),
        )

        try:
            persist_rows = db_sql(persist_sql)
        except Exception as exc:
            sys.stderr.write(f"practice: DB persistence failed: {exc}\n")
            self._respond(500, {"error": "database persistence error"})
            return

        attempt_id = int(persist_rows[0][0])
        created_at_val = str(persist_rows[0][1])

        self._respond(200, {
            "ok": True,
            "attempt_id": attempt_id,
            "student_id": student_id,
            "unit_id": unit_id,
            "passed": passed,
            "pass_count": pass_count,
            "total_checks": total_checks,
            "checks": check_results,
            "created_at": created_at_val,
        })

    def _handle_retrieval_attempt(self, unit_id_override: str | None = None) -> None:
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        unit_id = unit_id_override or payload.get("unit_id")
        seed_index = payload.get("seed_index")
        seed_prompt = payload.get("seed_prompt")
        answer = payload.get("answer")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(unit_id, str) or not UNIT_RE.match(unit_id):
            self._respond(422, {"error": "unit_id (x.y.z) is required"})
            return
        if not isinstance(seed_index, int) or seed_index < 0:
            self._respond(422, {"error": "seed_index (non-negative integer) is required"})
            return
        if not isinstance(answer, str) or not answer.strip():
            self._respond(422, {"error": "answer (non-empty string) is required"})
            return
        if len(answer.encode("utf-8")) > MAX_FILE_BYTES:
            self._respond(400, {"error": "answer_too_large"})
            return
        if "\0" in answer:
            self._respond(400, {"error": "binary_content_rejected"})
            return

        # 1. Enrollment Gate Authorization
        gate_sql = """BEGIN;
SELECT EXISTS (
    SELECT 1 FROM enrollments
    WHERE student_id = %d AND unit_id = %s AND status = 'active'
), EXISTS (
    SELECT 1 FROM students WHERE id = %d
);
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id)
        try:
            gate_rows = db_sql(gate_sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        is_enrolled = gate_rows[0][0] == "t" or gate_rows[0][0] is True
        student_exists = gate_rows[0][1] == "t" or gate_rows[0][1] is True

        if not student_exists:
            self._respond(404, {"error": "student_not_found"})
            return
        if not is_enrolled:
            self._respond(403, {"error": "not_enrolled", "message": f"Active enrollment required for unit {unit_id}"})
            return

        # 2. Retrieval seeds validation
        seeds = get_unit_retrieval_seeds(unit_id)
        if not seeds:
            self._respond(404, {"error": "retrieval seeds not found for unit"})
            return
        if seed_index >= len(seeds):
            self._respond(400, {"error": "seed_index_out_of_bounds", "max_index": len(seeds) - 1})
            return

        canonical_seed = seeds[seed_index]
        if not seed_prompt:
            seed_prompt = canonical_seed

        # 3. Grade retrieval answer via LLM proxy judge
        try:
            verdict_res, tokens_charged, excerpt_meta = grade_retrieval_answer(
                student_id=student_id,
                unit_id=unit_id,
                seed_index=seed_index,
                seed_prompt=canonical_seed,
                student_answer=answer.strip(),
            )
        except BudgetExceeded as exc:
            self._respond(429, {"error": "budget_exceeded", "message": str(exc)})
            return
        except MalformedJudgeError as exc:
            self._respond(502, {"error": "malformed_judge_response", "detail": str(exc)})
            return
        except UpstreamError as exc:
            self._respond(502, {"error": "upstream_failure", "detail": str(exc)})
            return
        except Exception as exc:
            sys.stderr.write(f"practice: retrieval grading failure: {exc}\n")
            self._respond(502, {"error": "retrieval_grading_error", "detail": str(exc)})
            return

        passed = (verdict_res["verdict"] == "pass")
        feedback = verdict_res["feedback"]
        evidence = verdict_res["evidence"]

        # 4. Atomic Persistence: retrieval_attempts row + events spine event in the same transaction.
        # S3.3: when a deterministic clock knob is set, created_at is stamped from the
        # override so re-check schedules can be proven at fixed clock points; production
        # keeps the database's now() default. The verdict_json gains additive excerpt
        # metadata (chars sent, sections chosen) so every attempt row is cost-auditable.
        now_override = practice_now_override()
        if now_override is not None:
            created_at_sql = sql_str(now_override.isoformat())
        else:
            created_at_sql = "now()"
        verdict_json_persist = dict(verdict_res)
        verdict_json_persist["excerpt"] = excerpt_meta
        verdict_json_str = json.dumps(verdict_json_persist)

        persist_sql = """BEGIN;
WITH att AS (
    INSERT INTO retrieval_attempts (
        student_id, unit_id, seed_index, seed_prompt, student_answer,
        passed, feedback, evidence, verdict_json, tokens_charged, created_at
    ) VALUES (
        %d, %s, %d, %s, %s, %s, %s, %s, %s::jsonb, %d, %s
    )
    RETURNING id, student_id, unit_id, seed_index, seed_prompt, passed, feedback, evidence, tokens_charged, created_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'practice.retrieval_graded',
           jsonb_build_object(
               'attempt_id', id,
               'student_id', student_id,
               'unit_id', unit_id::text,
               'seed_index', seed_index,
               'seed_prompt', seed_prompt,
               'passed', passed,
               'tokens_charged', tokens_charged
           )
    FROM att
    RETURNING id
)
SELECT id, created_at FROM att;
COMMIT;
""" % (
            student_id,
            sql_str(unit_id),
            seed_index,
            sql_str(canonical_seed),
            sql_str(answer.strip()),
            "true" if passed else "false",
            sql_str(feedback),
            sql_str(evidence),
            sql_str(verdict_json_str),
            tokens_charged,
            created_at_sql,
        )

        try:
            persist_rows = db_sql(persist_sql)
        except Exception as exc:
            sys.stderr.write(f"practice: retrieval DB persistence failed: {exc}\n")
            self._respond(500, {"error": "database persistence error"})
            return

        attempt_id = int(persist_rows[0][0])
        created_at_val = str(persist_rows[0][1])

        self._respond(200, {
            "ok": True,
            "attempt_id": attempt_id,
            "student_id": student_id,
            "unit_id": unit_id,
            "seed_index": seed_index,
            "seed_prompt": canonical_seed,
            "passed": passed,
            "feedback": feedback,
            "evidence": evidence,
            "tokens_charged": tokens_charged,
            "created_at": created_at_val,
            "excerpt": excerpt_meta,
        })

    def _handle_concierge_ask(self, unit_id_override: str | None = None) -> None:
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._respond(400, {"error": "invalid JSON"})
            return

        student_id = payload.get("student_id")
        unit_id = unit_id_override or payload.get("unit_id")
        question = payload.get("question")

        if not isinstance(student_id, int) or student_id <= 0:
            self._respond(422, {"error": "student_id (positive integer) is required"})
            return
        if not isinstance(unit_id, str) or not UNIT_RE.match(unit_id):
            self._respond(422, {"error": "unit_id (x.y.z) is required"})
            return
        if not isinstance(question, str) or not question.strip():
            self._respond(422, {"error": "question (non-empty string) is required"})
            return
        if len(question.encode("utf-8")) > MAX_FILE_BYTES:
            self._respond(400, {"error": "question_too_large"})
            return
        if "\0" in question:
            self._respond(400, {"error": "binary_content_rejected"})
            return

        # 1. Check student existence and active enrollment
        gate_sql = """BEGIN;
SELECT EXISTS (
    SELECT 1 FROM enrollments
    WHERE student_id = %d AND unit_id = %s AND status = 'active'
), EXISTS (
    SELECT 1 FROM students WHERE id = %d
);
ROLLBACK;
""" % (student_id, sql_str(unit_id), student_id)
        try:
            gate_rows = db_sql(gate_sql)
        except Exception:
            self._respond(500, {"error": "database error"})
            return

        is_enrolled = gate_rows[0][0] == "t" or gate_rows[0][0] is True
        student_exists = gate_rows[0][1] == "t" or gate_rows[0][1] is True

        if not student_exists:
            self._respond(404, {"error": "student_not_found"})
            return
        if not is_enrolled:
            self._respond(403, {"error": "not_enrolled", "message": f"Active enrollment required for unit {unit_id}"})
            return

        # 2. Call concierge engine (derive mode, compose prompt, call proxy)
        try:
            mode, mode_reason, answer, tokens_charged = ask_concierge(
                student_id=student_id,
                unit_id=unit_id,
                question=question.strip(),
            )
        except BudgetExceeded as exc:
            self._respond(429, {"error": "budget_exceeded", "message": str(exc)})
            return
        except UpstreamError as exc:
            self._respond(502, {"error": "upstream_failure", "detail": str(exc)})
            return
        except RuntimeError as exc:
            sys.stderr.write(f"practice: concierge configuration/content error: {exc}\n")
            self._respond(502, {"error": "concierge_prompt_not_found", "detail": str(exc)})
            return
        except Exception as exc:
            sys.stderr.write(f"practice: concierge processing failure: {exc}\n")
            self._respond(500, {"error": "concierge_error", "detail": str(exc)})
            return

        # 3. Atomic persistence: concierge_turns + concierge.answered spine event
        now_override = practice_now_override()
        if now_override is not None:
            created_at_sql = sql_str(now_override.isoformat())
        else:
            created_at_sql = "now()"

        persist_sql = """BEGIN;
WITH turn AS (
    INSERT INTO concierge_turns (
        student_id, unit_id, mode, question, answer, tokens_charged, created_at
    ) VALUES (
        %d, %s, %s, %s, %s, %d, %s
    )
    RETURNING id, student_id, unit_id, mode, question, answer, tokens_charged, created_at
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'concierge.answered',
           jsonb_build_object(
               'turn_id', id,
               'student_id', student_id,
               'unit_id', unit_id::text,
               'mode', mode,
               'tokens_charged', tokens_charged
           )
    FROM turn
    RETURNING id
)
SELECT id, created_at FROM turn;
COMMIT;
""" % (
            student_id,
            sql_str(unit_id),
            sql_str(mode),
            sql_str(question.strip()),
            sql_str(answer),
            tokens_charged,
            created_at_sql,
        )

        try:
            persist_rows = db_sql(persist_sql)
        except Exception as exc:
            sys.stderr.write(f"practice: concierge DB persistence failed: {exc}\n")
            self._respond(500, {"error": "database persistence error"})
            return

        turn_id = int(persist_rows[0][0])
        created_at_val = str(persist_rows[0][1])

        self._respond(200, {
            "ok": True,
            "turn_id": turn_id,
            "student_id": student_id,
            "unit_id": unit_id,
            "mode": mode,
            "mode_reason": mode_reason,
            "answer": answer,
            "tokens_charged": tokens_charged,
            "created_at": created_at_val,
        })


def main() -> None:
    port = int(os.environ.get("KEEL_PRACTICE_PORT", "8792"))
    if not app_token():
        sys.stderr.write("refusing to start: KEEL_ENROLL_SECRET not set\n")
        sys.exit(1)
    # Fail fast on a bad KEEL_DB_CMD.
    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
    server = ThreadingHTTPServer(("127.0.0.1", port), PracticeHandler)
    sys.stderr.write("practice grading service listening on 127.0.0.1:%d\n" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
