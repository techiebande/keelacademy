"""Loader for platform/models.yaml — the one tier-to-model mapping (M4.3).

Both the grading CLI (platform/cli/grader/llm.py) and the LLM proxy
(platform/grading/proxy/server.py) import this module instead of hardcoding
model names. The defaults below are the pre-M4.3 values and serve as the
fallback when the YAML file is missing or unparseable, so a damaged file can
never take grading down; a stderr note makes the fallback visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

PLATFORM_ROOT = Path(__file__).resolve().parent
MODELS_YAML = PLATFORM_ROOT / "models.yaml"

# Fallback = the last hardcoded tiers before models.yaml existed.
DEFAULT_MODEL_TIERS: dict[str, dict] = {
    "low": {"model": "gpt-4o-mini", "price_in": 0.15, "price_out": 0.60},
    "mid": {"model": "gpt-4.1", "price_in": 2.00, "price_out": 8.00},
    "high": {"model": "o3", "price_in": 2.00, "price_out": 8.00},
}


def load_model_tiers(path: Path | None = None) -> dict[str, dict]:
    """Return the tier -> {model, price_in, price_out} mapping.

    Falls back to DEFAULT_MODEL_TIERS (with a stderr note) when the file is
    missing, empty, or not a mapping of tiers.
    """
    source = Path(path) if path else MODELS_YAML
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        tiers = data["tiers"]
        if not isinstance(tiers, dict) or not tiers:
            raise ValueError("no tiers mapping")
        for info in tiers.values():
            if not isinstance(info, dict) or "model" not in info:
                raise ValueError(f"tier entry missing model: {info!r}")
        return dict(tiers)
    except Exception as exc:
        print(f"[models_loader] warning: {source} unusable ({exc}); "
              f"using built-in default tiers", file=sys.stderr)
        return {k: dict(v) for k, v in DEFAULT_MODEL_TIERS.items()}


def allowed_models(tiers: dict[str, dict] | None = None) -> tuple[str, ...]:
    """The proxy's model allowlist: every concrete model named by a tier."""
    tiers = tiers if tiers is not None else load_model_tiers()
    return tuple(dict.fromkeys(info["model"] for info in tiers.values()))


def _ensure_importable() -> None:
    """Make `import models_loader` work from platform/cli and platform/grading."""
    if str(PLATFORM_ROOT) not in sys.path:
        sys.path.insert(0, str(PLATFORM_ROOT))
