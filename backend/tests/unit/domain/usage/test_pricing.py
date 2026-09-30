"""Pricing: per-category cost, tiers, Coffer's supplement, labels."""

from __future__ import annotations

import pytest

from coffer.domain.usage.pricing import (
    BUNDLED_SNAPSHOT,
    ModelPrice,
    TokenCounts,
    estimate_cost,
    override_label,
    reported_label,
)


def test_every_category_is_charged_at_its_own_rate() -> None:
    price = ModelPrice(
        input=3, output=15, cache_write_5m=3.75, cache_write_1h=6, cache_read=0.3, web_search=10
    )
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


def test_a_tier_charges_every_token_once_input_passes_its_threshold() -> None:
    high = ModelPrice(input=10, output=40)
    price = ModelPrice(input=5, output=20, tiers=((200_000, high),))
    below = TokenCounts(input_tokens=150_000, cache_read_tokens=50_000, output_tokens=1_000)
    above = TokenCounts(input_tokens=150_000, cache_read_tokens=50_001, output_tokens=1_000)
    # Exactly at the threshold: the base rate (cache reads fall back to input).
    assert estimate_cost(below, price) == pytest.approx((200_000 * 5 + 1_000 * 20) / 1e6)
    assert estimate_cost(above, price) == pytest.approx((200_001 * 10 + 1_000 * 40) / 1e6)


@pytest.mark.parametrize(
    ("model", "rates"),
    [
        ("claude-opus-5-5", (4, 20, 0.20)),
        ("claude-sonnet-5-5", (2, 10, 0.20)),
        ("claude-fable-5-1", (10, 50, 0.25)),
        ("claude-mythos-5-1", (10, 50, 0.25)),
    ],
)
def test_coffers_supplement_carries_what_the_list_lacks(
    model: str, rates: tuple[float, float, float]
) -> None:
    price = BUNDLED_SNAPSHOT.lookup(model)
    assert price is not None
    assert (price.input, price.output, price.cache_read) == pytest.approx(rates)
    assert price.cache_write_5m == pytest.approx(rates[0] * 1.25)
    assert price.cache_write_1h == pytest.approx(rates[0] * 2)


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-5-5[1m]",
        "anthropic.claude-opus-5-5",
        "us.anthropic.claude-opus-5-5",
        "eu.anthropic.claude-opus-5-5-v1:0",
        "claude-opus-5-5@20250514",
        "claude-opus-5-5-20251001",
    ],
)
def test_lookup_strips_cloud_prefix_context_marker_and_version(model: str) -> None:
    assert BUNDLED_SNAPSHOT.lookup(model) == BUNDLED_SNAPSHOT.lookup("claude-opus-5-5")


def test_missing_cache_price_falls_back_to_input_rate() -> None:
    override = ModelPrice(input=2.0, output=8.0)
    tokens = TokenCounts(cache_read_tokens=1_000_000, web_search_requests=5)
    assert estimate_cost(tokens, override) == pytest.approx(2.0)


def test_each_source_has_its_own_label() -> None:
    assert override_label("conn1") == "override:conn1"
    assert reported_label("conn1") == "provider:conn1"
