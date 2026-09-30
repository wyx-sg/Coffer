"""The bundled price list: provider scope, history, tiers, the supplement."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.usage.bundled_prices import BundledPrices, compile_match
from coffer.domain.usage.pricing import ModelPrice, PriceSnapshot

DOC: dict[str, Any] = {
    "commit": "0123456789abcdef",
    "providers": [
        {
            "id": "anthropic",
            "name": "Anthropic",
            "api_pattern": r"https://api\.anthropic\.com",
            "model_match": {"contains": "claude"},
            "models": [
                {
                    "id": "claude-sonnet-9",
                    "match": {"starts_with": "claude-sonnet-9"},
                    "prices": [
                        {"prices": {"input_mtok": 2, "output_mtok": 10}},
                        {
                            "constraint": {"start_date": "2026-09-01"},
                            "prices": {
                                "input_mtok": {"base": 3, "tiers": [{"start": 200000, "price": 6}]},
                                "cache_write_mtok": 3.75,
                                "cache_read_mtok": 0.3,
                                "output_mtok": 15,
                            },
                        },
                    ],
                },
            ],
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "api_pattern": r"https://api\.openai\.com",
            "model_match": {"starts_with": "gpt-"},
            "models": [
                {
                    "id": "gpt-9",
                    "match": {"equals": "gpt-9"},
                    "prices": {"input_mtok": 1, "output_mtok": 8},
                }
            ],
        },
        {
            "id": "relay",
            "name": "Relay",
            "api_pattern": r"https://relay\.example",
            "fallback_model_providers": ["openai"],
            "models": [
                {
                    "id": "gpt-9",
                    "match": {"equals": "gpt-9"},
                    "prices": {"input_mtok": 2, "output_mtok": 16},
                }
            ],
        },
        {
            "id": "reseller",
            "name": "Reseller",
            "api_pattern": r"https://resell\.example",
            "fallback_model_providers": ["anthropic"],
            "models": [],
        },
    ],
}

LIST = BundledPrices.from_document(DOC, supplement=None)


def test_the_same_model_is_priced_at_the_provider_its_endpoint_names() -> None:
    vendor = LIST.lookup("gpt-9", base_url="https://api.openai.com/v1")
    relay = LIST.lookup("gpt-9", base_url="https://relay.example/v1")
    assert vendor is not None and (vendor.provider_name, vendor.price.input) == ("OpenAI", 1)
    assert relay is not None and (relay.provider_name, relay.price.input) == ("Relay", 2)


def test_an_endpoint_no_provider_claims_is_priced_by_the_models_vendor() -> None:
    found = LIST.lookup("gpt-9", base_url="https://gateway.acme.dev/v1")
    assert found is not None and found.provider_name == "OpenAI"


def test_a_reseller_falls_back_to_the_provider_it_resells() -> None:
    found = LIST.lookup("claude-sonnet-9", base_url="https://resell.example")
    assert found is not None and found.provider_name == "Anthropic"


def test_the_price_in_force_when_the_request_started_is_used() -> None:
    before = LIST.lookup("claude-sonnet-9", at=datetime(2026, 8, 31, tzinfo=UTC))
    after = LIST.lookup("claude-sonnet-9", at=datetime(2026, 9, 2, tzinfo=UTC))
    assert before is not None and (before.price.input, before.price.output) == (2, 10)
    assert after is not None and (after.price.input, after.price.output) == (3, 15)


def test_tiers_and_anthropic_cache_categories_are_read() -> None:
    found = LIST.lookup("claude-sonnet-9", at=datetime(2026, 9, 2, tzinfo=UTC))
    assert found is not None
    price = found.price
    assert (price.cache_write_5m, price.cache_read, price.cache_write_1h) == (3.75, 0.3, 6)
    assert price.at(200_001).input == 6
    assert price.at(200_000).input == 3


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an unknown model is marked unpriced, never zero",
)
@pytest.mark.parametrize("model", ["qwen3:8b", "unknown-model", "", None])
def test_a_model_nothing_knows_is_unpriced(model: str | None) -> None:
    assert LIST.lookup(model) is None


def test_the_supplement_wins_over_a_broader_pattern_but_not_an_exact_id() -> None:
    supplement = PriceSnapshot(
        version="s",
        prices={
            "claude-sonnet-9-5": ModelPrice(input=1, output=2),
            "claude-sonnet-9": ModelPrice(input=99, output=99),
        },
    )
    both = BundledPrices.from_document(DOC, supplement=supplement)
    newer = both.lookup("claude-sonnet-9-5")
    exact = both.lookup("claude-sonnet-9", at=datetime(2026, 9, 2, tzinfo=UTC))
    assert newer is not None and newer.price.input == 1
    assert exact is not None and exact.price.input == 3
    assert both.label == "bundled:genai-prices@0123456789ab+coffer@s"


def test_match_clauses() -> None:
    m = compile_match(
        {"or": [{"regex": "^o[34]"}, {"and": [{"contains": "x"}, {"ends_with": "y"}]}]}
    )
    assert m("o4-mini") and m("axy") and not m("ax") and not m("gpt")
