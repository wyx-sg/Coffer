"""Find the newest release of Coffer (spec daemon "Check the installed binaries
for a new release" and "Upgrade the installed binaries from the command line").

The desktop app checks a signed manifest itself. The installer's frozen
binaries have no shell to do that, so the daemon running from them asks the
GitHub API for the project's latest release — the same "latest, not a
pre-release" the app's manifest URL follows — once a minute after it starts and
then daily, the way the price list refreshes:

- one read-only ``GET`` of one fixed URL, with a timeout and a size cap, sending
  nothing about the user;
- a failure keeps the last result and is logged once per failure streak;
- ``update_check`` in ``~/.coffer/daemon-config.json`` (the About page's Check
  automatically switch) turns the periodic check off, and
  ``COFFER_UPDATE_CHECK=off`` pins it off (tests, CI).

``coffer update`` reads the same release with :func:`fetch_latest_sync`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.infrastructure.daemon.atomic_write import write_json_0600
from coffer.infrastructure.daemon.config import config_path

_logger = logging.getLogger(__name__)

REPO = "wyx-sg/Coffer"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
#: Where a tag's assets are downloaded from.
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/download"
#: A release's JSON is a few kilobytes; its notes are the only long field.
MAX_BYTES = 1024 * 1024
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FIRST_DELAY_SECONDS = 60.0
INTERVAL_SECONDS = 24 * 60 * 60.0
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "coffer-update-check"}

CHECK_ENV = "COFFER_UPDATE_CHECK"
_OFF = frozenset({"off", "false", "0", "no"})
_SETTING = "update_check"

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class Release:
    """One published release, as the About page and ``coffer update`` show it."""

    version: str
    tag: str
    notes: str
    published_at: str | None
    url: str


def version_key(version: str) -> tuple[int, int, int, int, str] | None:
    """A sortable key for a semver string (a leading ``v`` allowed); ``None``
    when it is not one. A pre-release sorts before its release."""
    match = _SEMVER.match(version.strip())
    if match is None:
        return None
    major, minor, patch, pre = match.groups()
    return (int(major), int(minor), int(patch), 0 if pre else 1, pre or "")


def is_newer(candidate: str, running: str) -> bool:
    """Whether ``candidate`` is a later version than ``running``; never for an
    unparseable one, so a malformed tag offers nothing."""
    new, old = version_key(candidate), version_key(running)
    return new is not None and old is not None and new > old


def parse_release(payload: Any) -> Release:
    """The release in a GitHub API ``releases/latest`` answer; raises ``ValueError``
    for anything that is not a published release with a semver tag."""
    if not isinstance(payload, dict):
        raise ValueError("the release answer is not an object")
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or version_key(tag) is None:
        raise ValueError(f"the latest release's tag {tag!r} is not a version")
    if payload.get("draft") or payload.get("prerelease"):
        raise ValueError("the latest release is a draft or a pre-release")
    notes = payload.get("body")
    published = payload.get("published_at")
    page = payload.get("html_url")
    return Release(
        version=tag.removeprefix("v"),
        tag=tag,
        notes=notes.strip() if isinstance(notes, str) else "",
        published_at=published if isinstance(published, str) else None,
        url=page if isinstance(page, str) else f"https://github.com/{REPO}/releases/tag/{tag}",
    )


def asset_url(tag: str, name: str) -> str:
    return f"{DOWNLOAD_BASE}/{tag}/{name}"


# --- fetching ----------------------------------------------------------------------


async def fetch_latest(url: str = LATEST_URL) -> Release:
    """GET the latest release: bounded in time and size, nothing about the user."""
    async with (
        httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client,
        client.stream("GET", url, headers=_HEADERS) as r,
    ):
        r.raise_for_status()
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError(f"release answer larger than {MAX_BYTES} bytes")
    return parse_release(json.loads(bytes(body)))


def fetch_latest_sync(url: str = LATEST_URL) -> Release:
    """:func:`fetch_latest` for the command line, which has no event loop."""
    with (
        httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client,
        client.stream("GET", url, headers=_HEADERS) as r,
    ):
        r.raise_for_status()
        body = bytearray()
        for chunk in r.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError(f"release answer larger than {MAX_BYTES} bytes")
    return parse_release(json.loads(bytes(body)))


# --- the setting -------------------------------------------------------------------


def _config() -> dict[str, Any]:
    try:
        payload = json.loads(config_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def check_pinned_off() -> bool:
    """``COFFER_UPDATE_CHECK=off`` in this process's environment."""
    return os.environ.get(CHECK_ENV, "").strip().lower() in _OFF


def read_check_setting() -> bool:
    """The machine's setting: on unless ``daemon-config.json`` says ``false``."""
    return _config().get(_SETTING) is not False


def write_check_setting(enabled: bool) -> None:
    """Record the setting, keeping every other key in the file; on is the default
    and is written as no key at all."""
    payload = {k: v for k, v in _config().items() if k != _SETTING}
    if not enabled:
        payload[_SETTING] = False
    write_json_0600(config_path(), payload)


# --- the daemon's check ------------------------------------------------------------


Fetcher = Callable[[], Awaitable[Release]]


class ReleaseCheck:
    """The newest release the daemon has found for the binaries it runs from.

    ``applies`` is false for a daemon from the desktop app or from source: it
    then never fetches, and only reports that it does not check.
    """

    def __init__(
        self,
        *,
        running: str,
        applies: bool,
        fetch: Fetcher | None = None,
        enabled: Callable[[], bool] = read_check_setting,
        pinned_off: Callable[[], bool] = check_pinned_off,
    ) -> None:
        self.running = running
        self.applies = applies
        self._fetch = fetch or fetch_latest
        self._enabled = enabled
        self._pinned_off = pinned_off
        self.latest: Release | None = None
        self.checked_at: datetime | None = None
        self.last_error: str | None = None
        self._failing = False
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    def auto_check(self) -> bool:
        return self._enabled()

    def checks(self) -> bool:
        """Whether this daemon checks at all (by hand or on the timer)."""
        return self.applies and not self._pinned_off()

    def available(self) -> Release | None:
        """The newest release found, when it is newer than the one running."""
        latest = self.latest
        return latest if latest is not None and is_newer(latest.version, self.running) else None

    async def check_now(self) -> bool:
        """Fetch the latest release once; ``False`` (and the last result kept) on
        any failure, or when this daemon does not check."""
        if not self.checks():
            return False
        async with self._lock:
            try:
                release = await self._fetch()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                if not self._failing:
                    _logger.warning("daemon.update_check_failed", extra={"error": self.last_error})
                self._failing = True
                return False
            self.latest = release
            self.checked_at = datetime.now(UTC)
            self.last_error = None
            if self._failing:
                _logger.info("daemon.update_check_recovered")
            self._failing = False
            return True

    async def run(
        self, first_delay: float = FIRST_DELAY_SECONDS, interval: float = INTERVAL_SECONDS
    ) -> None:
        """Check after ``first_delay``, then every ``interval``, while switched on."""
        if not self.checks():
            return
        self._stop.clear()
        delay = first_delay
        while not self._stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            if self._stop.is_set():
                return
            if self._enabled():
                await self.check_now()
            delay = interval

    def stop(self) -> None:
        self._stop.set()


__all__ = [
    "INTERVAL_SECONDS",
    "LATEST_URL",
    "Release",
    "ReleaseCheck",
    "asset_url",
    "check_pinned_off",
    "fetch_latest",
    "fetch_latest_sync",
    "is_newer",
    "parse_release",
    "read_check_setting",
    "version_key",
    "write_check_setting",
]
