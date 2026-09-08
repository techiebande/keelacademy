"""Unit tests for the proxy's per-unit budget cap (M5.4).

The proxy module is loaded by file path (it is not a package); db_sql is
never called by these tests — only the pure accounting functions are
exercised, plus the header the CLI sends to identify the unit.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROXY_PATH = (Path(__file__).resolve().parents[2]
              / "grading" / "proxy" / "server.py")


def load_proxy(monkeypatch, env_cap):
    monkeypatch.setenv("KEEL_UNIT_TOKENS_CAP", env_cap)
    spec = importlib.util.spec_from_file_location("proxy_server_ub", PROXY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cap_env_parsing(monkeypatch):
    mod = load_proxy(monkeypatch, "5000")
    assert mod.unit_tokens_cap() == 5000
    assert load_proxy(monkeypatch, "0").unit_tokens_cap() is None
    assert load_proxy(monkeypatch, "-3").unit_tokens_cap() is None
    assert load_proxy(monkeypatch, "junk").unit_tokens_cap() is None
    monkeypatch.delenv("KEEL_UNIT_TOKENS_CAP")
    assert mod.unit_tokens_cap() is None


def test_unit_blocks_only_after_cap_reached(monkeypatch):
    mod = load_proxy(monkeypatch, "100")
    mod._unit_used.clear()
    assert mod.unit_budget_allows("0.1") is True
    mod.unit_charge("0.1", 90)
    assert mod.unit_budget_allows("0.1") is True
    # Overshoot bound: the in-flight call that crosses the cap still
    # completes (mirrors the per-student rule), the next is blocked.
    mod.unit_charge("0.1", 20)
    assert mod.unit_budget_allows("0.1") is False


def test_units_are_independent(monkeypatch):
    mod = load_proxy(monkeypatch, "100")
    mod._unit_used.clear()
    mod.unit_charge("0.1", 100)
    assert mod.unit_budget_allows("0.1") is False
    assert mod.unit_budget_allows("0.2") is True


def test_no_cap_means_always_allowed(monkeypatch):
    monkeypatch.delenv("KEEL_UNIT_TOKENS_CAP", raising=False)
    spec = importlib.util.spec_from_file_location("proxy_server_nc", PROXY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._unit_used.clear()
    mod.unit_charge("0.1", 10_000_000)
    assert mod.unit_budget_allows("0.1") is True


def test_grading_cli_sends_unit_header(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # platform/cli
    from grader import llm

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        class R:
            def read(self):
                return (b'{"model":"m","usage":{"prompt_tokens":1,'
                        b'"completion_tokens":1},"choices":[{"message":'
                        b'{"content":"ok"}}]}')
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return R()

    monkeypatch.setenv("KEEL_LLM_STUDENT_ID", "7")
    monkeypatch.setenv("KEEL_LLM_UNIT_ID", "0.1")
    monkeypatch.setenv("KEEL_TRACE_LOG", "off")  # never touch the real trace file
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    llm.call_model("m", [{"role": "user", "content": "hi"}], "key")
    assert captured["headers"].get("X-keel-student-id") == "7"
    assert captured["headers"].get("X-keel-unit-id") == "0.1"
