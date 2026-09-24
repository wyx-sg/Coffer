"""The background worker that converges on an interval (spec vault-sync).

Shaped like ``RetentionWorker``: one catch-up round shortly after boot, then on
the remote's interval; a failing round is logged and never kills the loop.

Two things it deliberately does not do. It does not decide what is survivable —
``ConvergeService.run_once`` returns a status rather than raising, so the loop
has no judgement to make. And it does not skip a tick because the last round
was held at the deletion guard: the round re-derives its diff and releases a
hold whose breach has gone, which is how a vault stuck on a question that no
longer applies unsticks itself. Having the worker track that state would be a
second place for it to go stale — and would keep the vault stuck.

What it does not do *again* is say so. A hold the round reports as already
reported is logged at debug, because the warning belongs to the round that
first raised it: one outstanding confirmation, one line in the daemon log,
however long it stands.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from coffer.application.sync.ports import SyncRemoteRepoPort
from coffer.application.sync.service import ConvergeService
from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus

_logger = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first round.
DEFAULT_START_DELAY_S = 30.0
#: Fifteen minutes. Short enough that moving between machines rarely means
#: waiting, long enough that an idle vault is not committing noise — which it
#: cannot anyway, because an unchanged vault serializes to an unchanged tree.
DEFAULT_INTERVAL_S = 15 * 60.0


def _always_on() -> bool:
    return True


class ConvergeWorker:
    def __init__(
        self,
        service: ConvergeService,
        remotes: SyncRemoteRepoPort,
        *,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        default_interval_s: float = DEFAULT_INTERVAL_S,
        is_enabled: Callable[[], bool] = _always_on,
    ) -> None:
        self._service = service
        # Whether the vault_sync feature is on right now, read at the top of
        # every round (spec experimental-features "Close every surface of a
        # switched-off feature"): a round while it is off is skipped, not run.
        self._is_enabled = is_enabled
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
            await self.tick()
            await self._sleep(interval)

    async def tick(self) -> None:
        """One scheduled round, or nothing while the feature is switched off."""
        if not self._is_enabled():
            _logger.debug("converge: skipped, vault_sync is switched off")
            return
        try:
            run = await self._service.run_once()
        except Exception:  # the loop outlives any single round
            _logger.exception("converge: round raised")
        else:
            self._log(run)

    async def _interval(self) -> float:
        remote = await self._remotes.get()
        if remote is None or not remote.enabled:
            return self._default_interval
        return float(remote.interval_seconds or self._default_interval)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)

    @staticmethod
    def _log(run: ConvergeRun) -> None:
        quiet = run.status in (
            ConvergeStatus.OK,
            ConvergeStatus.NO_CHANGE,
            ConvergeStatus.DISABLED,
            # Waiting for the user to join is a state, not news: the Sync
            # page and ``coffer sync status`` say so; the log need not, every
            # interval.
            ConvergeStatus.AWAITING_JOIN,
        )
        if quiet or run.hold_already_reported:
            # A confirmation this vault has already reported is not news. It
            # was warned about when it was raised, and the user answers it on
            # the Sync page, not by reading the log an eleventh time.
            _logger.debug("converge: %s", run.status.value)
        else:
            # A conflict, or a situation that has just arisen, is waiting on
            # the user and worth saying out loud.
            _logger.warning("converge: %s", run.status.value)
