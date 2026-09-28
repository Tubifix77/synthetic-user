"""config.MODEL_TIERS is the single source of model choice.

CLAUDE.md promises that re-routing a role (e.g. the Adversary hat to another
family) is a config swap, not a code edit. That only holds while no module names
a model itself — a hardcoded ID silently wins over the config. This pins it.

FAST TEST — no LLM calls.
"""
import re
from pathlib import Path

from synthetic_user import config

_ROOT = Path(__file__).resolve().parents[1]
_MODEL_ID = re.compile(r"claude-(?:opus|sonnet|haiku)-\d")


def test_no_module_hardcodes_a_model_id():
    offenders = []
    for folder in ("synthetic_user", "hooks"):
        for path in (_ROOT / folder).rglob("*.py"):
            if path.name == "config.py":
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _MODEL_ID.search(line):
                    offenders.append(f"{path.relative_to(_ROOT)}:{n}: {line.strip()}")
    assert not offenders, "model IDs must come from config.model_for():\n" + "\n".join(offenders)


def test_every_role_resolves_to_a_concrete_model():
    for role in config.MODEL_TIERS:
        assert _MODEL_ID.match(config.model_for(role)), role


def test_env_override_reroutes_one_role(monkeypatch):
    monkeypatch.setenv("SYNTH_MODEL_HAT_ADVERSARY", "opus")
    assert config.model_for("hat_adversary") == config.MODELS["opus"]
    monkeypatch.setenv("SYNTH_MODEL_HAT_ADVERSARY", "some-other-family-model")
    assert config.model_for("hat_adversary") == "some-other-family-model"
    assert config.model_for("hat_correctness") == config.MODELS[config.MODEL_TIERS["hat_correctness"]]


def test_subscription_friendly_defaults():
    # Rate limits are the ceiling on a subscription: nothing defaults to Opus.
    assert "opus" not in config.MODEL_TIERS.values()
    assert config.MODEL_TIERS["hat_adversary"] != config.MODEL_TIERS["hat_correctness"], (
        "the Adversary hat must sit on a different tier from Correctness (bias diversity)"
    )
