"""Subscription quota: keep the latest official value of each window (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

Values arrive from three places and are stored the same way — latest per
(agent type, window), each with the moment its source produced it:

* Coffer-driven chat turns push them: Claude Code's ``rate_limit_event`` and
  Codex's ``account/rateLimits/updated`` reach :meth:`QuotaService.observe_agent_event`
  through the chat adapters' quota observer.
* The opt-in statusline wrapper forwards Claude Code's ``rate_limits``
  (:meth:`observe_statusline`).
* Codex is also PULLED with ``account/rateLimits/read`` (:meth:`refresh_codex`):
  in the background at most every five minutes while enabled, and on a manual
  refresh at most every 30 seconds.

Nothing is estimated. A window whose ``resets_at`` has passed no longer says
anything about now, so :meth:`latest` reports it without a number — only when
it was last seen.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from coffer.application.usage.ports import (
    Clock,
    CodexRateLimitReader,
    QuotaRepo,
    StoredQuotaWindow,
    SystemClock,
)
from coffer.domain.usage.quota import (
    CLAUDE_AGENT_TYPE,
    CODEX_AGENT_TYPE,
    QuotaSnapshot,
    from_claude_rate_limit_event,
    from_codex_rate_limits,
    from_statusline,
)

_logger = logging.getLogger(__name__)

#: The agent types a subscription quota can exist for, in display order.
QUOTA_AGENT_TYPES: tuple[str, ...] = (CLAUDE_AGENT_TYPE, CODEX_AGENT_TYPE)

#: Background Codex reads: never more often than this.
BACKGROUND_INTERVAL = timedelta(minutes=5)
#: A manual refresh may read sooner, but never more often than this.
FORCED_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True)
class QuotaWindowView:
    """One window as the Usage page shows it. ``used_percent`` is ``None`` when
    the window has reset since it was observed (``stale``)."""

    key: str
    label: str
    used_percent: float | None
    window_minutes: int | None
    resets_at: datetime | None
    as_of: datetime
    source: str
    stale: bool


@dataclass(frozen=True)
class AgentQuotaView:
    """Every window known for one agent type; empty when none was ever seen."""

    agent_type: str
    plan: str | None
    windows: list[QuotaWindowView]
    last_observed_at: datetime | None


@dataclass(frozen=True)
class RefreshOutcome:
    """Whether a Codex read happened, and why not when it did not."""

    refreshed: bool
    reason: str | None = None


class QuotaService:
    def __init__(
        self,
        *,
        repo: QuotaRepo,
        codex_reader: CodexRateLimitReader | None = None,
        clock: Clock | None = None,
        background_enabled: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._repo = repo
        self._codex = codex_reader
        self._clock = clock or SystemClock()
        self._background_enabled = background_enabled
        self._last_codex_read: datetime | None = None
        self._read_lock = asyncio.Lock()
        self._stop = asyncio.Event()

    # -- push ----------------------------------------------------------------

    async def observe(self, snapshot: QuotaSnapshot | None) -> bool:
        """Store ``snapshot``'s windows as the latest for their keys; ``False``
        when the feed carried no usable window (nothing is stored)."""
        if snapshot is None:
            return False
        await self._repo.upsert(snapshot)
        return True

    async def observe_claude_event(self, raw: Mapping[str, Any]) -> bool:
        return await self.observe(from_claude_rate_limit_event(raw, observed_at=self._clock.now()))

    async def observe_statusline(self, rate_limits: Mapping[str, Any]) -> bool:
        return await self.observe(from_statusline(rate_limits, observed_at=self._clock.now()))

    async def observe_codex_update(self, params: Mapping[str, Any]) -> bool:
        return await self.observe(from_codex_rate_limits(params, observed_at=self._clock.now()))

    async def observe_agent_event(self, agent_type: str, payload: dict[str, Any]) -> None:
        """The chat adapters' quota observer: ``("claude_code", rate_limit_info.raw)``
        or ``("codex", account/rateLimits/updated params)``."""
        if agent_type == CLAUDE_AGENT_TYPE:
            await self.observe_claude_event(payload)
        elif agent_type == CODEX_AGENT_TYPE:
            await self.observe_codex_update(payload)

    # -- pull ----------------------------------------------------------------

    async def refresh_codex(self, *, force: bool = False) -> RefreshOutcome:
        """Read Codex's official windows now, unless one was read too recently
        (five minutes; 30 seconds when ``force``d by a manual refresh)."""
        if self._codex is None:
            return RefreshOutcome(False, "codex_unavailable")
        async with self._read_lock:
            now = self._clock.now()
            floor = FORCED_INTERVAL if force else BACKGROUND_INTERVAL
            if self._last_codex_read is not None and now - self._last_codex_read < floor:
                return RefreshOutcome(False, "too_soon")
            # Counted from the attempt, not the success, so a failing read is
            # not retried in a tight loop either.
            self._last_codex_read = now
            try:
                result = await self._codex.read()
            except Exception:
                _logger.warning("usage.quota.codex_read_failed", exc_info=True)
                return RefreshOutcome(False, "read_failed")
            if result is None:
                return RefreshOutcome(False, "no_subscription")
            snapshot = from_codex_rate_limits(result, observed_at=self._clock.now())
            if snapshot is None:
                return RefreshOutcome(False, "no_windows")
            await self.observe(snapshot)
            return RefreshOutcome(True)

    async def run(self, interval: float = BACKGROUND_INTERVAL.total_seconds()) -> None:
        """Read Codex every ``interval`` seconds while enabled, until :meth:`stop`."""
        self._stop.clear()
        while not self._stop.is_set():
            try:
                if self._codex is not None and await self._enabled():
                    await self.refresh_codex()
            except Exception:
                _logger.exception("usage.quota.background_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval)

    def stop(self) -> None:
        self._stop.set()

    async def _enabled(self) -> bool:
        return True if self._background_enabled is None else await self._background_enabled()

    # -- read ----------------------------------------------------------------

    async def latest(self) -> list[AgentQuotaView]:
        """Every quota agent type, with what is known of each (possibly nothing)."""
        now = self._clock.now()
        by_agent: dict[str, list[StoredQuotaWindow]] = {}
        for row in await self._repo.latest():
            by_agent.setdefault(row.agent_type, []).append(row)
        agent_types = list(QUOTA_AGENT_TYPES) + sorted(set(by_agent) - set(QUOTA_AGENT_TYPES))
        views: list[AgentQuotaView] = []
        for agent_type in agent_types:
            rows = sorted(by_agent.get(agent_type, []), key=_window_order)
            newest = max(rows, key=lambda r: r.observed_at) if rows else None
            views.append(
                AgentQuotaView(
                    agent_type=agent_type,
                    plan=newest.plan if newest else None,
                    windows=[_view(r, now) for r in rows],
                    last_observed_at=newest.observed_at if newest else None,
                )
            )
        return views


def _window_order(row: StoredQuotaWindow) -> tuple[int, str]:
    return (row.window_minutes if row.window_minutes is not None else 1 << 30, row.key)


def _view(row: StoredQuotaWindow, now: datetime) -> QuotaWindowView:
    stale = row.resets_at is not None and row.resets_at <= now
    return QuotaWindowView(
        key=row.key,
        label=row.label,
        used_percent=None if stale else row.used_percent,
        window_minutes=row.window_minutes,
        resets_at=row.resets_at,
        as_of=row.observed_at,
        source=str(row.source),
        stale=stale,
    )


__all__ = [
    "BACKGROUND_INTERVAL",
    "FORCED_INTERVAL",
    "QUOTA_AGENT_TYPES",
    "AgentQuotaView",
    "QuotaService",
    "QuotaWindowView",
    "RefreshOutcome",
]
