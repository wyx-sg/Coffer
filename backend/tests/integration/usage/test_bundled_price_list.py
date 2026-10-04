"""The price list shipped in the build parses and prices what it should."""

from __future__ import annotations

import pytest

from coffer.infrastructure.usage.bundled_prices import DATA_FILE, load_bundled_prices


def test_the_vendored_list_and_its_licence_ship_together() -> None:
    assert DATA_FILE.is_file()
    licence = DATA_FILE.with_name("genai-prices.LICENSE").read_text("utf-8")
    assert "MIT License" in licence


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a known model is priced per category",
)
def test_a_known_model_is_priced_per_category() -> None:
    found = load_bundled_prices().lookup("claude-sonnet-4-6", base_url="https://api.anthropic.com")
    assert found is not None and found.provider_name == "Anthropic"
    price = found.price
    assert (price.input, price.output) == (3, 15)
    assert (price.cache_write_5m, price.cache_write_1h, price.cache_read) == pytest.approx(
        (3.75, 6, 0.3)
    )


def test_openai_models_are_bundled_now() -> None:
    found = load_bundled_prices().lookup("gpt-5", base_url="https://api.openai.com/v1")
    assert found is not None and found.provider_name == "OpenAI"
    assert found.price.input > 0 and found.price.output > 0
