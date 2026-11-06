"""The daily refresh of the model price list (spec provider-switching "Refresh
the bundled price list in the background").

Every build ships a snapshot of pydantic/genai-prices
(:mod:`.bundled_prices`). Prices change between releases, so the daemon also
fetches the list genai-prices publishes — the same file its own
``UpdatePrices`` fetches — once shortly after it starts and then every 24
hours, the way LiteLLM and genai-prices refresh theirs:

- a read-only ``GET`` of one fixed URL Coffer chose (:data:`UPDATE_URL`), with
  a timeout and a size cap, sending nothing about the user;
- the payload is validated before it is kept, then cached atomically at
  ``~/.coffer/derived/genai-prices.json`` with when it was fetched;
- pricing uses whichever of the cache and the bundled snapshot is fresher, and
  never waits on the network: a failed fetch keeps what is there, and is
  logged once per failure streak, not on every tick;
- ``price_refresh`` in ``~/.coffer/daemon-config.json`` (the Settings page's price-refresh switch)
  turns it off on a firewalled machine;
  ``COFFER_PRICE_REFRESH=off`` pins it off (tests, CI).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from coffer.domain.usage.bundled_prices import BundledPrices, validate_payload
from coffer.infrastructure.daemon.atomic_write import write_json_0600
from coffer.infrastructure.daemon.config import config_path
from coffer.infrastructure.vault.home import derived_root

_logger = logging.getLogger(__name__)

#: What genai-prices' own ``UpdatePrices`` fetches (``DEFAULT_UPDATE_URL``).
UPDATE_URL = (
    "https://raw.githubusercontent.com/pydantic/genai-prices/refs/heads/main/"
    "prices/new_data/v2/data.json"
)
#: The published file is about 0.5 MB; anything past this is not the price list.
MAX_BYTES = 16 * 1024 * 1024
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
#: The first fetch waits this long after start, so a daemon start is not slowed.
FIRST_DELAY_SECONDS = 60.0
INTERVAL_SECONDS = 24 * 60 * 60.0

REFRESH_ENV = "COFFER_PRICE_REFRESH"
_OFF = frozenset({"off", "false", "0", "no"})
_SETTING = "price_refresh"


def default_cache_path() -> Path:
    return derived_root() / "genai-prices.json"


# --- the setting ---------------------------------------------------------------


def _config() -> dict[str, Any]:
    try:
        payload = json.loads(config_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def refresh_pinned_off() -> bool:
    """``COFFER_PRICE_REFRESH=off`` in this process's environment."""
    return os.environ.get(REFRESH_ENV, "").strip().lower() in _OFF


def read_refresh_setting() -> bool:
    """The machine's setting: on unless ``daemon-config.json`` says ``false``."""
    return _config().get(_SETTING) is not False


def refresh_enabled() -> bool:
    """Whether the refresh runs: the setting, unless the environment pins it off."""
    return not refresh_pinned_off() and read_refresh_setting()


def write_refresh_setting(enabled: bool | None) -> None:
    """Record the setting; ``None`` returns it to the default (on). Keeps every
    other key in the file."""
    payload = {k: v for k, v in _config().items() if k != _SETTING}
    if enabled is not None:
        payload[_SETTING] = enabled
    write_json_0600(config_path(), payload)


# --- fetching --------------------------------------------------------------------


async def fetch_payload(url: str = UPDATE_URL) -> Any:
    """GET the published list: bounded in time and size, no credentials, no
    cookies, nothing about the user. Raises on any failure."""
    async with (
        httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client,
        client.stream("GET", url, headers={"User-Agent": "coffer-price-refresh"}) as r,
    ):
        r.raise_for_status()
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError(f"price list larger than {MAX_BYTES} bytes")
    return json.loads(bytes(body))


Fetcher = Callable[[], Awaitable[Any]]


@dataclass
class RefreshStatus:
    last_attempt_at: datetime | None = None
    last_error: str | None = None


class PriceListSource:
    """The price list pricing reads now: the fresher of the refreshed cache and
    the bundled snapshot. Reads never touch the network."""

    def __init__(
        self,
        bundled: BundledPrices,
        *,
        cache_path: Path | None = None,
        fetch: Fetcher | None = None,
        enabled: Callable[[], bool] = refresh_enabled,
    ) -> None:
        self._bundled = bundled
        self._cache_path = cache_path or default_cache_path()
        self._fetch = fetch or fetch_payload
        self._enabled = enabled
        self._cached: BundledPrices | None = self._load_cache()
        self.status = RefreshStatus()
        self._failing = False
        self._stop = asyncio.Event()

    def _load_cache(self) -> BundledPrices | None:
        try:
            document = json.loads(self._cache_path.read_text("utf-8"))
            validate_payload(document.get("providers"))
            return BundledPrices.from_document(document)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, AttributeError):
            _logger.warning("usage.price_cache_unreadable", extra={"file": str(self._cache_path)})
            return None

    def current(self) -> BundledPrices:
        """The list to price from: the cache when it is at least as new as the
        bundled snapshot, else the snapshot."""
        cached = self._cached
        if cached is None or cached.updated is None:
            return self._bundled
        if self._bundled.updated is not None and cached.updated < self._bundled.updated:
            return self._bundled
        return cached

    def enabled(self) -> bool:
        return self._enabled()

    async def refresh_once(self) -> bool:
        """Fetch, validate and cache the list once. ``False`` (and the old list
        kept) on any failure."""
        now = datetime.now(UTC)
        self.status.last_attempt_at = now
        try:
            providers = validate_payload(await self._fetch())
            document = {"source": UPDATE_URL, "fetched_at": now.isoformat(), "providers": providers}
            fresh = BundledPrices.from_document(document)
            await asyncio.to_thread(write_json_0600, self._cache_path, document)
        except Exception as exc:
            self.status.last_error = f"{type(exc).__name__}: {exc}"[:300]
            if not self._failing:
                _logger.warning(
                    "usage.price_refresh_failed", extra={"error": self.status.last_error}
                )
            self._failing = True
            return False
        self._cached = fresh
        self.status.last_error = None
        if self._failing:
            _logger.info("usage.price_refresh_recovered")
        self._failing = False
        return True

    async def run(
        self,
        first_delay: float = FIRST_DELAY_SECONDS,
        interval: float = INTERVAL_SECONDS,
    ) -> None:
        """Refresh after ``first_delay``, then every ``interval``, while enabled."""
        self._stop.clear()
        delay = first_delay
        while not self._stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            if self._stop.is_set():
                return
            if self._enabled():
                await self.refresh_once()
            delay = interval

    def stop(self) -> None:
        self._stop.set()


__all__ = [
    "INTERVAL_SECONDS",
    "MAX_BYTES",
    "UPDATE_URL",
    "PriceListSource",
    "fetch_payload",
    "read_refresh_setting",
    "refresh_enabled",
    "refresh_pinned_off",
    "write_refresh_setting",
]
