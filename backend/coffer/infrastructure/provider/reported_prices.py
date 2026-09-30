"""The prices endpoints' APIs reported, kept between listings.

A derived file, ``~/.coffer/derived/reported-prices.json``: written when a
provider's models are listed or refreshed, read when usage is costed and when
the Models section shows a price (spec provider-switching "Resolve each
model's price from the provider, its API, or the bundled list"). Never
synced, never authoritative — losing it only means the next listing fills it
again, and until then a model falls back to the bundled price.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.application.provider.ports import ReportedPrices
from coffer.domain.usage.pricing import ModelPrice
from coffer.infrastructure.vault.home import derived_root

_logger = logging.getLogger(__name__)

_FIELDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read", "web_search")


def default_path() -> Path:
    return derived_root() / "reported-prices.json"


def _encode(price: ModelPrice) -> dict[str, float]:
    return {k: v for k in _FIELDS if (v := getattr(price, k)) is not None}


def _decode(data: Mapping[str, Any]) -> ModelPrice | None:
    def rate(key: str) -> float | None:
        value = data.get(key)
        return None if value is None else float(value)

    try:
        return ModelPrice(
            input=float(data["input"]),
            output=float(data["output"]),
            cache_write_5m=rate("cache_write_5m"),
            cache_write_1h=rate("cache_write_1h"),
            cache_read=rate("cache_read"),
            web_search=rate("web_search"),
        )
    except (KeyError, TypeError, ValueError):
        return None


class FileReportedPriceStore:
    """``ReportedPriceStore`` over one JSON file, cached in memory."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_path()
        self._lock = threading.Lock()
        self._cache: dict[str, ReportedPrices] | None = None

    def _load(self) -> dict[str, ReportedPrices]:
        if self._cache is not None:
            return self._cache
        entries: dict[str, ReportedPrices] = {}
        try:
            raw = json.loads(self._path.read_text("utf-8"))
        except (OSError, ValueError):
            raw = {}
        for root, entry in (raw.get("endpoints") or {}).items():
            try:
                fetched = datetime.fromisoformat(str(entry["fetched_at"]))
            except (KeyError, ValueError):
                continue
            prices = {
                model: price
                for model, value in (entry.get("prices") or {}).items()
                if (price := _decode(value)) is not None
            }
            entries[root] = ReportedPrices(fetched_at=fetched, prices=prices)
        self._cache = entries
        return entries

    def get(self, root: str) -> ReportedPrices | None:
        with self._lock:
            return self._load().get(root)

    def put(self, root: str, prices: Mapping[str, ModelPrice]) -> None:
        with self._lock:
            entries = dict(self._load())
            entries[root] = ReportedPrices(fetched_at=datetime.now(UTC), prices=dict(prices))
            self._cache = entries
            document = {
                "endpoints": {
                    r: {
                        "fetched_at": e.fetched_at.isoformat(),
                        "prices": {m: _encode(p) for m, p in e.prices.items()},
                    }
                    for r, e in entries.items()
                }
            }
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".tmp")
                tmp.write_text(json.dumps(document, indent=1), "utf-8")
                os.replace(tmp, self._path)
            except OSError:
                _logger.warning("provider.reported_prices_write_failed", exc_info=True)


@functools.cache
def _store_at(path: Path) -> FileReportedPriceStore:
    return FileReportedPriceStore(path)


def shared_store() -> FileReportedPriceStore:
    """The one store for this home: the listing that writes it and the meter
    that reads it must share one in-memory copy."""
    return _store_at(default_path())


__all__ = ["FileReportedPriceStore", "default_path", "shared_store"]
