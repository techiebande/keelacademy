"""Shared LLM-call infrastructure for the grading CLIs (judge, defend).

Key convention: OPENAI_API_KEY from the environment only (never hardcoded,
never on disk). Stdlib urllib only — no openai-package dependency.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Base URL is overridable so calls can be routed through the grading LLM proxy
# (S1.8) without forking any caller logic: the judge just runs with
# KEEL_LLM_BASE_URL=http://...<proxy>/v1. The proxy enforces per-student
# budgets and attaches the platform key itself, so a key is only required on
# the direct-to-OpenAI path.
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _base_url() -> str:
    return os.environ.get("KEEL_LLM_BASE_URL") or DEFAULT_BASE_URL


def _routed_via_proxy() -> bool:
    return bool(os.environ.get("KEEL_LLM_BASE_URL"))


API_TIMEOUT_S = 180

DEFAULT_TRACE_LOG = Path.home() / ".keelacademy-traces.jsonl"

# Trace context (S1.7): the caller tag is set once by each CLI entry point
# (judge/defend/calibrate/gate); the tier is set by whoever resolves the
# model_tier. Inner layers set only what they own, so calibrate/gate runs keep
# their tag while judge() fills in the tier underneath them. The environment
# defaults let an orchestrating process (the S1.8 queue worker spawning the
# judge) stamp its own caller tag and a per-grading-call correlation id without
# touching CLI logic.
_caller_var = contextvars.ContextVar(
    "keel_trace_caller", default=os.environ.get("KEEL_TRACE_CALLER"))
_tier_var = contextvars.ContextVar("keel_trace_tier", default=None)
# attempt ordinal: every raw call_model within one logical grading call gets
# the next number (JSON-nudge retries and transient retries both advance it),
# so a retried call is visible as attempt 2, 3, ... in the trace. Reset at the
# outermost call site (each CLI run; each submission in calibrate/gate).
_attempt_var = contextvars.ContextVar("keel_trace_attempt", default=0)


def begin_trace_call() -> None:
    """Reset the attempt ordinal; call at the start of one logical grading
    call (before any retry loop that may invoke call_model repeatedly)."""
    _attempt_var.set(0)


def set_trace_caller(name: str, force: bool = False) -> None:
    if force or _caller_var.get() is None:
        _caller_var.set(name)


def set_trace_tier(tier: str | None) -> None:
    _tier_var.set(tier)

# model_tier -> concrete model + prices now live in ONE place: platform/models.yaml
# (M4.3). The loader keeps these pre-M4.3 values as the fallback; llm.py and
# the grading proxy both read the file through it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # platform/
from models_loader import load_model_tiers  # noqa: E402

MODEL_TIERS = load_model_tiers()

NUDGE = (
    "Your previous reply was not valid JSON. Return ONLY a single JSON object "
    "conforming to the schema from the original prompt — no markdown fences, "
    "no commentary before or after."
)


class LLMError(Exception):
    pass


class LLMBudgetExceeded(LLMError):
    """The endpoint answered 429 budget_exceeded (the grading proxy's
    per-student cutoff). Distinct from a generic failure so callers can
    record a budget-blocked outcome instead of a grading error."""
    pass


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    tier_info = next(
        (v for v in MODEL_TIERS.values() if model == v["model"] or model.startswith(v["model"] + "-")),
        {"price_in": 0.0, "price_out": 0.0},
    )
    return (prompt_tokens * tier_info["price_in"]
            + completion_tokens * tier_info["price_out"]) / 1_000_000


def _trace_dest() -> Path | None:
    """KEEL_TRACE_LOG names the file; 'off' or empty disables; unset -> default
    in the user's home (never inside the repo)."""
    value = os.environ.get("KEEL_TRACE_LOG")
    if value is None:
        return DEFAULT_TRACE_LOG
    value = value.strip()
    if not value or value.lower() == "off":
        return None
    return Path(value)


def _append_trace(record: dict) -> None:
    """One JSON line per raw LLM call. Never breaks grading: a trace failure
    prints one stderr warning and the call proceeds."""
    try:
        dest = _trace_dest()
        if dest is None:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[trace] warning: failed to write trace record to "
              f"{os.environ.get('KEEL_TRACE_LOG', str(DEFAULT_TRACE_LOG))}: {exc}",
              file=sys.stderr)


def _trace_record(attempt: int, model: str, messages: list[dict],
                  latency_s: float, prompt_tokens: int = 0, completion_tokens: int = 0,
                  response: str | None = None, error: str | None = None) -> None:
    served = model
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "caller": _caller_var.get() or "unknown",
        "model": served,
        "tier": _tier_var.get(),
        "attempt": attempt,
        "latency_s": round(latency_s, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(_estimate_cost(served, prompt_tokens, completion_tokens), 6),
        "prompt": messages,
        "response": response,
        "error": error,
    }
    call_id = os.environ.get("KEEL_TRACE_CALL_ID")
    if call_id:
        record["call_id"] = call_id
    _append_trace(record)


def call_model(model: str, messages: list[dict], api_key: str) -> tuple[str, dict]:
    attempt = _attempt_var.get() + 1
    _attempt_var.set(attempt)
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # Through the grading proxy the caller's identity is the student whose
    # budget is charged (X-Keel-Student-Id); direct calls carry no such header.
    student_id = os.environ.get("KEEL_LLM_STUDENT_ID")
    if student_id:
        headers["X-Keel-Student-Id"] = student_id
    # The unit whose per-unit budget (M5.4) is charged; set per grading call
    # by the orchestrating worker. Absent on direct calls and when unset.
    unit_id = os.environ.get("KEEL_LLM_UNIT_ID")
    if unit_id:
        headers["X-Keel-Unit-Id"] = unit_id
    req = urllib.request.Request(
        _base_url().rstrip("/") + "/chat/completions", data=payload,
        method="POST", headers=headers,
    )
    start = time.monotonic()
    try:
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_S) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code == 429:
                raise LLMBudgetExceeded(f"API HTTP 429: {detail}") from exc
            raise LLMError(f"API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"API unreachable: {exc}") from exc
        except OSError as exc:
            # Connection resets / read timeouts surface here (resp.read() raises
            # raw OSError subclasses, not URLError) — wrap so callers can retry.
            raise LLMError(f"API connection failed: {exc}") from exc
        latency = time.monotonic() - start
        usage = body.get("usage", {})
        text = body["choices"][0]["message"]["content"]
        meta = {
            "model": body.get("model", model),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "latency_s": round(latency, 2),
        }
        _trace_record(attempt, meta["model"], messages, latency,
                      meta["prompt_tokens"], meta["completion_tokens"], response=text)
        return text, meta
    except Exception as exc:
        # Error record (500-char truncation matches the LLMError convention),
        # then re-raise — tracing never swallows or alters the failure. The
        # key is redacted defensively: the API can echo it back inside error
        # bodies (observed live on a 401 with an invalid key).
        err = str(exc)[:500].replace(api_key, "<redacted>")
        _trace_record(attempt, model, messages, time.monotonic() - start,
                      error=err)
        raise


def call_with_json_retry(model: str, messages: list[dict], api_key: str) -> tuple[dict, dict]:
    """Call the model; on malformed JSON retry once with the nudge, then raise."""
    messages = list(messages)
    for attempt in (1, 2):
        text, meta = call_model(model, messages, api_key)
        try:
            return extract_json(text), meta
        except (ValueError, json.JSONDecodeError):
            if attempt == 2:
                raise LLMError(f"model returned malformed JSON twice; last reply:\n{text[:500]}")
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": NUDGE},
            ]
    raise LLMError("unreachable")


def extract_json(text: str) -> dict:
    """Parse the model's reply, tolerating markdown code fences."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = m.group(1) if m else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in reply")
    return json.loads(candidate[start:end + 1])


def require_api_key() -> str:
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        if _routed_via_proxy():
            # Routed through the grading proxy: it holds the platform key, so
            # the caller needs none (calls are authorized by student budget).
            return ""
        raise LLMError("OPENAI_API_KEY not set in the environment")
    return api_key


def trace(meta: dict) -> None:
    cost = _estimate_cost(meta["model"], meta["prompt_tokens"], meta["completion_tokens"])
    print(f"[trace] model={meta['model']} tokens_in={meta['prompt_tokens']} "
          f"tokens_out={meta['completion_tokens']} latency={meta['latency_s']}s "
          f"cost≈${cost:.5f}", file=sys.stderr)
