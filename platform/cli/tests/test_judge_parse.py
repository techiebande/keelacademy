"""Offline tests for the Layer-2 judge's parsing and recomputation rules.

No LLM is called: call_with_json_retry is monkeypatched to return canned model
output, so these tests pin the CONTRACT the model must speak (criteria array,
id agreement, model-overall agreement) and the CLI's own verdict arithmetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # platform/cli
from grader import judge as judge_mod  # noqa: E402
from grader.judge import (JudgeError, build_prompt, judge, load_rubric,  # noqa: E402
                          resolve_prompt_path)
from grader.submission import gather_submission  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
RUBRIC_01 = REPO_ROOT / "content" / "rubrics" / "0.1" / "v1.yaml"

FAKE_META = {
    "model": "test-model",
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "latency_s": 0.01,
}


def criteria_payload(rubric: dict, verdict: str = "pass") -> list[dict]:
    return [
        {"id": c["id"], "verdict": verdict, "evidence": f"quoted words for {c['id']}"}
        for c in rubric["criteria"]
    ]


@pytest.fixture()
def submission_dir(tmp_path: Path) -> Path:
    (tmp_path / "brief.md").write_text("OmniCart gets 400 return requests a month.")
    (tmp_path / "grade.yaml").write_text("answers: never shown to the model")
    return tmp_path


@pytest.fixture()
def patched_llm(monkeypatch):
    def install(parsed_response):
        monkeypatch.setattr(judge_mod, "require_api_key", lambda: "test-key")
        monkeypatch.setattr(
            judge_mod,
            "call_with_json_retry",
            lambda model, messages, api_key: (parsed_response, dict(FAKE_META, model=model)),
        )

    return install


def rubric_01() -> dict:
    return yaml.safe_load(RUBRIC_01.read_text())


def test_build_prompt_substitutes_rubric_insert_marker():
    prompt = build_prompt(
        {"id": "r", "version": 1},
        "RUBRIC BODY",
        "Intro line.\n<!-- RUBRIC_INSERT -->\nRules.",
        "SUBMISSION TEXT",
    )
    assert "RUBRIC BODY" in prompt
    assert "RUBRIC_INSERT" not in prompt
    assert "SUBMISSION TEXT" in prompt
    # The submission is always fenced so prose addressed to the judge cannot
    # escape into the prompt structure.
    assert "```\nSUBMISSION TEXT\n```" in prompt


def test_build_prompt_appends_rubric_when_marker_missing():
    prompt = build_prompt({"id": "r", "version": 1}, "RUBRIC BODY", "No marker here.", "SUB")
    assert "## Rubric (verbatim)" in prompt
    assert "RUBRIC BODY" in prompt


def test_load_rubric_rejects_missing_keys(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: r\nversion: 1\n")
    with pytest.raises(JudgeError, match="missing key"):
        load_rubric(bad)


def test_resolve_prompt_path_finds_prompt_near_rubric():
    prompt = resolve_prompt_path(RUBRIC_01, "prompts/judge-0.1.md")
    assert prompt.name == "judge-0.1.md"
    assert prompt.is_file()


def test_gather_submission_excludes_answers(tmp_path: Path):
    (tmp_path / "extract.py").write_text("print('hi')")
    (tmp_path / "grade.yaml").write_text("answers: secret")
    text = gather_submission(tmp_path)
    assert "print('hi')" in text
    assert "secret" not in text


def test_judge_recomputes_all_pass_overall(patched_llm, submission_dir):
    rubric = rubric_01()
    parsed = {"criteria": criteria_payload(rubric), "overall": "pass"}
    patched_llm(parsed)
    verdict = judge(submission_dir, RUBRIC_01)
    assert verdict["overall"] == "pass"
    assert [c["verdict"] for c in verdict["criteria"]] == ["pass"] * len(rubric["criteria"])


def test_judge_recomputes_one_fail_overall(patched_llm, submission_dir):
    rubric = rubric_01()
    crit = criteria_payload(rubric)
    crit[0]["verdict"] = "fail"
    parsed = {"criteria": crit, "overall": "fail"}
    patched_llm(parsed)
    verdict = judge(submission_dir, RUBRIC_01)
    assert verdict["overall"] == "fail"


def test_judge_rejects_criterion_id_divergence(patched_llm, submission_dir):
    rubric = rubric_01()
    crit = criteria_payload(rubric)
    crit[0]["id"] = "invented-criterion"
    patched_llm({"criteria": crit, "overall": "fail"})
    with pytest.raises(JudgeError, match="criterion ids diverge"):
        judge(submission_dir, RUBRIC_01)


def test_judge_rejects_model_overall_disagreement(patched_llm, submission_dir):
    rubric = rubric_01()
    # Model says overall pass while one criterion fails: the CLI must reject.
    crit = criteria_payload(rubric)
    crit[1]["verdict"] = "fail"
    patched_llm({"criteria": crit, "overall": "pass"})
    with pytest.raises(JudgeError, match="disagrees with recomputed"):
        judge(submission_dir, RUBRIC_01)
