"""The background worker that runs the memory sync (spec memory "Sync on an
interval and on demand").

One sync at daemon start, then one per interval. Both the switch and the
interval are read per pass, so a change in Settings — or one arriving from
another machine through vault sync — applies without a restart. The switch is
off by default: the sync writes into the agents' own memory, so the person
turns it on.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.upkeep_clock import PASS_CLOCK, PassClock
from coffer.application.upkeep_schedule import (
    DEFAULT_INTERVALS,
    IntervalReader,
    wait_for_next_pass,
)
from coffer.domain.internal_engine_config import MEMORY_SYNC
from coffer.domain.memory.errors import MemorySyncRunning

logger = logging.getLogger(__name__)

#: The actor an unattended sync is recorded under.
WORKER_ACTOR = "system:memory-sync-worker"

SyncCallable = Callable[[str], Awaitable[object]]
EnabledCheck = Callable[[], Awaitable[bool]]


class MemorySyncWorker:
    def __init__(
        self,
        *,
        sync: SyncCallable,
        is_enabled: EnabledCheck,
        read_interval: IntervalReader,
        clock: PassClock = PASS_CLOCK,
    ) -> None:
        self._sync = sync
        self._is_enabled = is_enabled
        self._read_interval = read_interval
        self._clock = clock

    async def run_forever(self) -> None:
        while True:
            self._clock.running(MEMORY_SYNC)
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except MemorySyncRunning:
                logger.debug("memory.sync_worker.already_running")
            except Exception:
                logger.warning("memory.sync_worker.pass_failed", exc_info=True)
            self._clock.waiting(MEMORY_SYNC)
            await wait_for_next_pass(self._read_interval, default_s=DEFAULT_INTERVALS[MEMORY_SYNC])

    async def run_once(self) -> None:
        if not await self._is_enabled():
            return
        await self._sync(WORKER_ACTOR)


__all__ = ["WORKER_ACTOR", "MemorySyncWorker"]
