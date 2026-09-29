"""Pricing: per-category cost, lookup normalisation, unpriced models."""

from __future__ import annotations

import pytest

from coffer.domain.usage.pricing import (
    BUNDLED_SNAPSHOT,
    ModelPrice,
    TokenCounts,
    estimate_cost,
    override_label,
)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a known model is priced per category",
)
def test_known_model_is_priced_per_category() -> None:
    price = BUNDLED_SNAPSHOT.lookup("claude-sonnet-4-6")
    assert price is not None
    tokens = TokenCounts(
        input_tokens=1_000_000,
        cache_write_5m_tokens=1_000_000,
        cache_write_1h_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        output_tokens=1_000_000,
        web_search_requests=1_000,
    )
    # 3 + 3.75 + 6 + 0.30 + 15 + 10 (web search, $10 per 1k)
    assert estimate_cost(tokens, price) == pytest.approx(38.05)


@pytest.mark.parametrize(
    ("model", "cache_read"),
    [
        ("claude-opus-5-5", 0.20),
        ("claude-sonnet-5-5", 0.20),
        ("claude-fable-5-1", 0.25),
        ("claude-mythos-5-1", 0.25),
        ("claude-opus-4-6", 0.5),
        ("claude-haiku-4-5", 0.1),
    ],
)
def test_cache_read_rate_is_model_specific(model: str, cache_read: float) -> None:
    price = BUNDLED_SNAPSHOT.lookup(model)
    assert price is not None
    assert price.cache_read == pytest.approx(cache_read)


def test_input_output_rates_of_the_bundled_snapshot() -> None:
    expected = {
        "claude-fable-5-1": (10, 50),
        "claude-fable-5": (10, 50),
        "claude-mythos-5-1": (10, 50),
        "claude-opus-5-5": (4, 20),
        "claude-opus-5": (5, 25),
        "claude-opus-4-8": (5, 25),
        "claude-opus-4-7": (5, 25),
        "claude-opus-4-6": (5, 25),
        "claude-sonnet-5-5": (2, 10),
        "claude-sonnet-5": (2, 10),
        "claude-sonnet-4-6": (3, 15),
        "claude-haiku-4-5": (1, 5),
    }
    for model, (inp, out) in expected.items():
        price = BUNDLED_SNAPSHOT.lookup(model)
        assert price is not None, model
        assert (price.input, price.output) == (inp, out)
        assert price.cache_write_5m == pytest.approx(inp * 1.25)
        assert price.cache_write_1h == pytest.approx(inp * 2)
    assert BUNDLED_SNAPSHOT.label == "snapshot:2026-09-25"


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-6[1m]",
        "anthropic.claude-opus-4-6",
        "us.anthropic.claude-opus-4-6",
        "eu.anthropic.claude-opus-4-6-v1:0",
        "global.anthropic.claude-opus-4-6[1m]",
        "claude-opus-4-6@20250514",
        "claude-opus-4-6-20251001",
    ],
)
def test_lookup_strips_cloud_prefix_context_marker_and_version(model: str) -> None:
    assert BUNDLED_SNAPSHOT.lookup(model) == BUNDLED_SNAPSHOT.lookup("claude-opus-4-6")


@pytest.mark.parametrize("model", ["gpt-5.5-codex", "o4-mini", "unknown-model", "", None])
@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an unknown model is marked unpriced, never zero",
)
def test_unknown_model_is_unpriced_not_zero(model: str | None) -> None:
    # No OpenAI prices are bundled: such a model needs a connection override.
    assert BUNDLED_SNAPSHOT.lookup(model) is None


def test_missing_cache_price_falls_back_to_input_rate() -> None:
    override = ModelPrice(input=2.0, output=8.0)
    tokens = TokenCounts(cache_read_tokens=1_000_000, web_search_requests=5)
    assert estimate_cost(tokens, override) == pytest.approx(2.0)
    assert override_label("conn1") == "override:conn1"
