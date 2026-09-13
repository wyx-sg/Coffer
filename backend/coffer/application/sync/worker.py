"""The background worker that converges on an interval (spec vault-sync).

Shaped like ``RetentionWorker``: one catch-up round shortly after boot, then on
the remote's interval; a failing round is logged and never kills the loop.

Two things it deliberately does not do. It does not decide what is survivable —
``ConvergeService.run_once`` returns a status rather than raising, so the loop
has no judgement to make. And it does not skip a tick because the last round
was held at the deletion guard: a held round returns immediately and cheaply,
and having the worker track that state would be a second place for it to go
stale.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from coffer.application.sync.ports import SyncRemoteRepoPort
from coffer.application.sync.service import ConvergeService
from coffer.domain.sync.convergence import ConvergeStatus

_logger = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first round.
DEFAULT_START_DELAY_S = 30.0
#: Fifteen minutes. Short enough that moving between machines rarely means
#: waiting, long enough that an idle vault is not committing noise — which it
#: cannot anyway, because an unchanged vault serializes to an unchanged tree.
DEFAULT_INTERVAL_S = 15 * 60.0


class ConvergeWorker:
    def __init__(
        self,
        service: ConvergeService,
        remotes: SyncRemoteRepoPort,
        *,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        default_interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        self._service = service
        self._remotes = remotes
        self._start_delay = start_delay_s
        self._default_interval = default_interval_s
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
        await self._sleep(self._start_delay)
        while not self._stop.is_set():
            interval = await self._interval()
            try:
                run = await self._service.run_once()
            except Exception:  # the loop outlives any single round
                _logger.exception("converge: round raised")
            else:
                self._log(run.status)
            await self._sleep(interval)

    async def _interval(self) -> float:
        remote = await self._remotes.get()
        if remote is None or not remote.enabled:
            return self._default_interval
        return float(remote.interval_seconds or self._default_interval)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)

    @staticmethod
    def _log(status: ConvergeStatus) -> None:
        if status in (ConvergeStatus.OK, ConvergeStatus.NO_CHANGE, ConvergeStatus.DISABLED):
            _logger.debug("converge: %s", status.value)
        else:
            # A conflict or a held round is waiting on the user, so it is worth
            # saying out loud every time rather than once.
            _logger.warning("converge: %s", status.value)
