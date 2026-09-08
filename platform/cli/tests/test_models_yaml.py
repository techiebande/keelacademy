"""Tests for platform/models.yaml — the single tier-to-model source (M4.3)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # platform/
from models_loader import (DEFAULT_MODEL_TIERS, MODELS_YAML,  # noqa: E402
                           allowed_models, load_model_tiers)


def test_shipped_models_yaml_parses_and_covers_default_tiers():
    tiers = load_model_tiers()
    assert set(tiers) >= {"low", "mid", "high"}
    for tier, info in tiers.items():
        assert info["model"], f"tier {tier} has no model"


def test_missing_file_falls_back_to_defaults(tmp_path: Path, capsys):
    tiers = load_model_tiers(tmp_path / "nope.yaml")
    assert tiers == DEFAULT_MODEL_TIERS
    assert "warning" in capsys.readouterr().err


def test_unusable_file_falls_back_to_defaults(tmp_path: Path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("tiers: [not, a, mapping]\n")
    assert load_model_tiers(bad) == DEFAULT_MODEL_TIERS
    assert "warning" in capsys.readouterr().err


def test_override_file_is_honored(tmp_path: Path):
    custom = tmp_path / "custom.yaml"
    custom.write_text("tiers:\n  low: {model: my-model}\n")
    tiers = load_model_tiers(custom)
    assert tiers["low"]["model"] == "my-model"


def test_allowed_models_derives_from_tiers():
    assert allowed_models({"a": {"model": "m1"}, "b": {"model": "m1"}, "c": {"model": "m2"}}) == ("m1", "m2")


def test_grading_cli_llm_reads_the_file():
    """llm.MODEL_TIERS must come from models.yaml, not a second hardcoded copy."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # platform/cli
    from grader import llm
    assert llm.MODEL_TIERS == load_model_tiers()
    assert MODELS_YAML.is_file()
