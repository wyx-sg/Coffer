"""Where a model's price comes from: you set → local → the provider's API →
bundled → none (spec provider-switching "Resolve each model's price from the
provider, its API, or the bundled list")."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.ports import ListedModel, ReportedPrices
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.usage.bundled_prices import BundledPrices
from coffer.domain.usage.pricing import ModelPrice, PriceSource
from coffer.infrastructure.provider.introspector import reported_price

BUNDLED = BundledPrices.from_document(
    {
        "commit": "c0ffee",
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI",
                "api_pattern": r"https://api\.openai\.com",
                "model_match": {"starts_with": "gpt-"},
                "models": [
                    {
                        "id": "gpt-9",
                        "match": {"starts_with": "gpt-9"},
                        "prices": {"input_mtok": 1, "output_mtok": 8},
                    }
                ],
            }
        ],
    },
    supplement=None,
)


class _Store:
    def __init__(self) -> None:
        self.data: dict[str, ReportedPrices] = {}

    def get(self, root: str) -> ReportedPrices | None:
        return self.data.get(root)

    def put(self, root: str, prices: Mapping[str, ModelPrice]) -> None:
        self.data[root] = ReportedPrices(fetched_at=datetime.now(UTC), prices=dict(prices))


def _row(uid: str, config: dict[str, Any]) -> Resource:
    return Resource(
        uid=uid,
        kind="provider",
        name=uid,
        config=ProviderConfig.model_validate(config).model_dump(mode="json"),
        enabled=True,
        description=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _Service:
    def __init__(self, *rows: Resource) -> None:
        self.rows = {r.uid: r for r in rows}

    async def get(self, uid: str) -> Resource:
        return self.rows[uid]

    @staticmethod
    def _cfg(resource: Resource) -> ProviderConfig:
        return ProviderConfig.model_validate(resource.config)


GATEWAY = _row(
    "gw",
    {
        "protocol": "openai",
        "base_url": "https://gw.example/v1",
        "credential_ref": "provider/x/key",
        "models": [{"id": "gpt-9", "price": {"input": 2, "output": 3}}, {"id": "gpt-9-mini"}],
    },
)
LOCAL = _row(
    "ollama",
    {
        "protocol": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "local_runtime": {"runtime": "ollama", "wires": ["openai"]},
    },
)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a price is taken from the first source that has one",
)
async def test_each_source_in_order() -> None:
    store = _Store()
    store.put("https://gw.example", {"gpt-9": ModelPrice(9, 9), "gpt-9-mini": ModelPrice(0.5, 1)})
    resolver = ProviderPriceResolver(_Service(GATEWAY, LOCAL), BUNDLED, store)  # type: ignore[arg-type]
    got = await resolver.resolve_many("gw", ["gpt-9", "gpt-9-mini", "gpt-9-nano", "other"])
    you_set, reported, bundled, none = (
        got[m] for m in ("gpt-9", "gpt-9-mini", "gpt-9-nano", "other")
    )
    assert you_set is not None and (you_set.source, you_set.price.input) == (PriceSource.USER, 2)
    assert you_set.label == "override:gw"
    assert reported is not None and (reported.source, reported.source_name) == (
        PriceSource.PROVIDER,
        "gw",
    )
    assert reported.label == "provider:gw"
    assert bundled is not None and (bundled.source, bundled.source_name) == (
        PriceSource.BUNDLED,
        "OpenAI",
    )
    assert none is None
    local = await resolver.resolve("ollama", "gpt-9", datetime.now(UTC))
    assert local is not None and (local.source, local.price.input, local.label) == (
        PriceSource.LOCAL,
        0.0,
        "local",
    )


async def test_a_listing_remembers_what_the_api_reported() -> None:
    store = _Store()

    class _Port:
        async def list_models(self, *, provider, base_url, api_key):  # type: ignore[no-untyped-def]
            return [ListedModel("a", ModelPrice(1, 2)), ListedModel("b"), "c"]

    svc = ModelIntrospectionService(_Port(), lambda _ref: "k", reported_prices=store)  # type: ignore[arg-type]
    listed = await svc.list_models(
        provider="openai", base_url="https://openrouter.ai/api/v1", credential_ref="r"
    )
    assert [m.id for m in listed.models] == ["a", "b", "c"]
    assert dict(store.data["https://openrouter.ai/api"].prices) == {"a": ModelPrice(1, 2)}


def test_openrouter_pricing_is_read_per_million_tokens() -> None:
    price = reported_price(
        {
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000015",
                "input_cache_read": "0.0000003",
            }
        }
    )
    assert price is not None
    assert (price.input, price.output, price.cache_read) == pytest.approx((3, 15, 0.3))
    assert reported_price({"pricing": {"prompt": "-1", "completion": "0"}}) is None
    assert reported_price({}) is None
