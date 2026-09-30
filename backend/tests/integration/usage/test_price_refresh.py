"""The daily price-list refresh (spec provider-switching "Refresh the bundled
price list in the background"): fetch, validate, cache, fall back, switch off."""

from __future__ import annotations

import copy
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from coffer.domain.usage.bundled_prices import BundledPrices
from coffer.infrastructure.usage.bundled_prices import DATA_FILE
from coffer.infrastructure.usage.price_refresh import (
    PriceListSource,
    read_refresh_setting,
    refresh_enabled,
    write_refresh_setting,
)

BUNDLED_DOC: dict[str, Any] = json.loads(DATA_FILE.read_text("utf-8"))
MODEL = "claude-sonnet-4-6"


def _bundled() -> BundledPrices:
    return BundledPrices.from_document(BUNDLED_DOC)


def _published(input_price: float) -> list[dict[str, Any]]:
    """What genai-prices publishes, with MODEL's input price changed."""
    providers = copy.deepcopy(BUNDLED_DOC["providers"])
    anthropic = next(p for p in providers if p["id"] == "anthropic")
    model = next(m for m in anthropic["models"] if m["id"] == MODEL)
    model["prices"] = {"input_mtok": input_price, "output_mtok": 15}
    return providers


def _input(source: PriceListSource) -> float:
    found = source.current().lookup(MODEL, base_url="https://api.anthropic.com")
    assert found is not None
    return found.price.input


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a refreshed list is cached and used",
)
async def test_a_fetched_list_is_validated_cached_and_used(tmp_path: Path) -> None:
    cache = tmp_path / "derived" / "genai-prices.json"

    async def fetch() -> Any:
        return _published(2.5)

    source = PriceListSource(_bundled(), cache_path=cache, fetch=fetch, enabled=lambda: True)
    assert _input(source) == 3
    assert await source.refresh_once() is True
    assert _input(source) == 2.5
    assert source.current().refreshed
    assert source.current().updated == datetime.now(UTC).date()
    written = json.loads(cache.read_text("utf-8"))
    assert written["fetched_at"] and written["providers"]
    # A daemon started later reads the cache without fetching.
    later = PriceListSource(_bundled(), cache_path=cache, fetch=fetch, enabled=lambda: False)
    assert _input(later) == 2.5


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a failed refresh keeps the list in use",
)
async def test_a_failed_fetch_keeps_what_is_there_and_logs_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    calls = {"n": 0}

    async def fetch() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            return _published(2.5)
        if calls["n"] == 2:
            raise OSError("network is unreachable")
        return {"not": "a provider array"}

    cache = tmp_path / "genai-prices.json"
    source = PriceListSource(_bundled(), cache_path=cache, fetch=fetch, enabled=lambda: True)
    assert await source.refresh_once()
    before = cache.read_text("utf-8")
    with caplog.at_level(logging.WARNING):
        assert await source.refresh_once() is False
        assert await source.refresh_once() is False
    assert _input(source) == 2.5
    assert cache.read_text("utf-8") == before
    assert source.status.last_error
    failures = [r for r in caplog.records if r.getMessage() == "usage.price_refresh_failed"]
    assert len(failures) == 1


async def test_nothing_fetched_ever_means_the_bundled_list(tmp_path: Path) -> None:
    async def fetch() -> Any:
        raise TimeoutError

    source = PriceListSource(
        _bundled(), cache_path=tmp_path / "c.json", fetch=fetch, enabled=lambda: True
    )
    assert await source.refresh_once() is False
    assert not source.current().refreshed
    assert _input(source) == 3


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the fresher of the cache and the bundled list is used",
)
@pytest.mark.parametrize(
    ("fetched_at", "uses_cache"), [("2099-01-01", True), ("2001-01-01", False)]
)
def test_the_fresher_list_wins(tmp_path: Path, fetched_at: str, uses_cache: bool) -> None:
    cache = tmp_path / "genai-prices.json"
    cache.write_text(
        json.dumps({"fetched_at": f"{fetched_at}T00:00:00+00:00", "providers": _published(1.0)}),
        "utf-8",
    )
    source = PriceListSource(_bundled(), cache_path=cache, enabled=lambda: False)
    assert source.current().refreshed is uses_cache
    assert _input(source) == (1.0 if uses_cache else 3)


def test_an_unreadable_cache_is_ignored(tmp_path: Path) -> None:
    cache = tmp_path / "genai-prices.json"
    cache.write_text("{not json", "utf-8")
    source = PriceListSource(_bundled(), cache_path=cache, enabled=lambda: False)
    assert not source.current().refreshed


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the refresh can be turned off",
)
async def test_the_refresh_turned_off_fetches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("COFFER_PRICE_REFRESH", raising=False)
    assert read_refresh_setting() is True
    write_refresh_setting(False)
    assert read_refresh_setting() is False and refresh_enabled() is False
    write_refresh_setting(None)
    assert refresh_enabled() is True
    monkeypatch.setenv("COFFER_PRICE_REFRESH", "off")
    assert refresh_enabled() is False

    fetched: list[int] = []

    async def fetch() -> Any:
        fetched.append(1)
        return _published(2.5)

    source = PriceListSource(
        _bundled(), cache_path=tmp_path / "c.json", fetch=fetch, enabled=lambda: False
    )
    import asyncio

    task = asyncio.create_task(source.run(first_delay=0, interval=0.01))
    await asyncio.sleep(0.1)
    source.stop()
    await task
    assert fetched == []


async def test_the_fetch_is_a_bounded_get_of_the_fixed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from coffer.infrastructure.usage import price_refresh

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.query == b"big":
            return httpx.Response(200, content=b"[" + b" " * (price_refresh.MAX_BYTES + 1) + b"]")
        return httpx.Response(200, json=[{"id": "x", "models": []}])

    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(price_refresh.httpx, "AsyncClient", client)
    assert await price_refresh.fetch_payload() == [{"id": "x", "models": []}]
    assert seen[0].method == "GET" and str(seen[0].url) == price_refresh.UPDATE_URL
    assert "authorization" not in seen[0].headers and "cookie" not in seen[0].headers
    with pytest.raises(ValueError, match="larger than"):
        await price_refresh.fetch_payload(price_refresh.UPDATE_URL + "?big")
