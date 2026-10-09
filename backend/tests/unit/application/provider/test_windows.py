"""Where a provider model's context window comes from: you set → the endpoint
→ the bundled list → unknown (spec provider-switching "Resolve each provider
model's context window")."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.provider.projection_request import projected_models
from coffer.application.provider.windows import ProviderWindowResolver
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.model_window import ResolvedWindow, WindowSource
from coffer.domain.usage.bundled_prices import BundledPrices

BUNDLED = BundledPrices.from_document(
    {
        "commit": "c0ffee",
        "providers": [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "api_pattern": r"https://api\.deepseek\.com",
                "models": [
                    {
                        "id": "deepseek-flash",
                        "match": {"equals": "deepseek-flash"},
                        "context_window": 1_000_000,
                        "prices": {"input_mtok": 1, "output_mtok": 2},
                    },
                    {
                        "id": "deepseek-old",
                        "match": {"equals": "deepseek-old"},
                        "prices": {"input_mtok": 1, "output_mtok": 2},
                    },
                ],
            }
        ],
    },
    supplement=None,
)


def _cfg(models: list[dict[str, Any]]) -> ProviderConfig:
    return ProviderConfig.model_validate(
        {
            "protocol": "anthropic",
            "base_url": "https://api.deepseek.com/anthropic",
            "secret_ref": "ref",
            "models": models,
        }
    )


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a model's window comes from you, then the endpoint, then the bundled list",
)
def test_a_models_window_comes_from_you_then_the_endpoint_then_the_bundled_list() -> None:
    resolver = ProviderWindowResolver(BUNDLED)
    cfg = _cfg(
        [
            {"id": "deepseek-flash", "context_window": 128_000, "user_context_window": 64_000},
            {"id": "endpoint-said", "context_window": 128_000},
            {"id": "deepseek-old"},
        ]
    )
    assert resolver.for_config(cfg, "deepseek-flash") == ResolvedWindow(64_000, WindowSource.USER)
    assert resolver.for_config(cfg, "endpoint-said") == ResolvedWindow(
        128_000, WindowSource.ENDPOINT
    )
    # Not curated at all (an unrestricted connection): the bundled list still knows it.
    assert resolver.for_config(_cfg([]), "deepseek-flash") == ResolvedWindow(
        1_000_000, WindowSource.BUNDLED
    )
    # The list prices it but records no window, and nothing else does: unknown.
    assert resolver.for_config(cfg, "deepseek-old") is None
    assert resolver.for_config(cfg, "agnes-2.5-pro-alpha") is None


def test_the_projection_is_handed_the_resolved_windows() -> None:
    resolver = ProviderWindowResolver(BUNDLED)
    cfg = _cfg([{"id": "deepseek-flash"}, {"id": "endpoint-said", "context_window": 200_000}])
    models = projected_models(cfg, resolver.tokens)
    assert [(m.id, m.context_window) for m in models] == [
        ("deepseek-flash", 1_000_000),
        ("endpoint-said", 200_000),
    ]
