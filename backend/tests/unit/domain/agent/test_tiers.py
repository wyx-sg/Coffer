"""Coffer's suggestion for Claude Code's tier pins (spec provider-switching
"Suggest a model for each Claude Code tier")."""

from __future__ import annotations

import pytest

from coffer.domain.agent.tiers import suggest_tier_models, tier_env_key


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a non-Claude connection pins every tier to the model"
)
def test_a_non_claude_connection_pins_every_tier_to_the_model() -> None:
    tiers = suggest_tier_models("kimi-k3", ["kimi-k3", "kimi-k3-mini"])
    assert tiers == {"opus": "kimi-k3", "sonnet": "kimi-k3", "haiku": "kimi-k3"}
    assert "fable" not in tiers


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a Claude-id gateway matches each tier by name"
)
def test_a_claude_id_gateway_matches_each_tier_by_name() -> None:
    curated = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5", "claude-fable-1"]
    assert suggest_tier_models("claude-sonnet-5-5", curated) == {
        "opus": "claude-opus-5-5",
        "sonnet": "claude-sonnet-5-5",
        "haiku": "claude-haiku-5",
        "fable": "claude-fable-1",
    }


def test_a_gateway_missing_a_tier_falls_back_to_the_model() -> None:
    assert suggest_tier_models("claude-opus-5-5", ["claude-opus-5-5"])["haiku"] == (
        "claude-opus-5-5"
    )


def test_a_local_runtime_pins_everything_to_its_one_model() -> None:
    tiers = suggest_tier_models("qwen3-coder", ["qwen3-coder", "claude-haiku-like"], local=True)
    assert set(tiers.values()) == {"qwen3-coder"}


def test_no_model_means_no_pins() -> None:
    assert suggest_tier_models(None, ["a"]) == {}
    assert tier_env_key("haiku") == "ANTHROPIC_DEFAULT_HAIKU_MODEL"
