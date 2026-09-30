"""Rounds on the remote's interval (spec vault-sync "Allow at most one
user-owned sync remote").

One round shortly after the daemon starts, then one every
``interval_seconds`` of the configured remote, re-read before each wait so a
changed interval is believed without a restart. Nothing runs while no remote
is configured or the remote is paused. A round that raises is logged and never
ends the loop; every other outcome is a recorded round the service already
reported. The round shares the vault's one lock with the curation pass, so
the timer waits for a pass rather than running beside it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coffer.domain.sync.remote import DEFAULT_INTERVAL_SECONDS, SyncRemote
from coffer.domain.sync.rounds import RoundRecord

_log = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first round.
START_DELAY_S = 30.0
#: How often a vault with no remote (or a paused one) looks again.
IDLE_POLL_S = 60.0


class _Rounds(Protocol):
    def remote(self) -> SyncRemote | None: ...
    def set_next_round(self, when: datetime | None) -> None: ...
    async def run(self, *, trigger: str = ...) -> RoundRecord: ...


class SyncWorker:
    def __init__(
        self,
        service: _Rounds,
        *,
        start_delay_s: float = START_DELAY_S,
        idle_poll_s: float = IDLE_POLL_S,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._service = service
        self._start_delay = start_delay_s
        self._idle_poll = idle_poll_s
        self._clock = clock
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        self._service.set_next_round(self._clock() + timedelta(seconds=self._start_delay))
        await self._sleep(self._start_delay)
        while not self._stop.is_set():
            wait = await self.tick()
            await self._sleep(wait)

    async def tick(self) -> float:
        """One scheduled round when a remote is on; answers how long to wait."""
        remote = self._service.remote()
        if remote is None or not remote.enabled:
            self._service.set_next_round(None)
            return self._idle_poll
        try:
            await self._service.run(trigger="timer")
        except Exception:  # the loop outlives any single round
            _log.exception("sync.round_raised")
        interval = float(
            (self._service.remote() or remote).interval_seconds or DEFAULT_INTERVAL_SECONDS
        )
        self._service.set_next_round(self._clock() + timedelta(seconds=interval))
        return interval

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)


__all__ = ["IDLE_POLL_S", "START_DELAY_S", "SyncWorker"]
