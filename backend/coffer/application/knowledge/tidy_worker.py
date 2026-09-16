"""The background worker that runs the tidy pass on an interval.

It is off unless the operator turns it on. That default is the point rather
than caution: the pass rewrites files a human and an agent manage together,
with no diff to approve before it lands (spec knowledge FR-051), so an
unattended rewriter should be something the operator switched on, never
something they discover running.

Shaped like ``RetentionWorker``: one catch-up pass shortly after boot, then on
an interval; a failing pass is logged and never kills the loop; a pending pass
never blocks shutdown, because the tidy is idempotent and the next boot sweeps
everything again.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UPKEEP_RUNS, UpkeepRunRegistry
from coffer.application.upkeep_schedule import IntervalReader, wait_for_next_pass

logger = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first pass.
DEFAULT_START_DELAY_S = 60.0
DEFAULT_INTERVAL_S = 6 * 60 * 60.0

TidyCallable = Callable[..., Awaitable[dict[str, object]]]
EnabledCheck = Callable[[], Awaitable[bool]]
CollectionLister = Callable[[], Awaitable[list[str]]]


async def _unset_interval() -> int | None:
    """No interval chosen — the constant above applies. The composition root
    injects a reader of the operator's setting instead."""
    return None


class TidyWorker:
    def __init__(
        self,
        *,
        service: KnowledgeService,
        tidy: TidyCallable,
        is_enabled: EnabledCheck,
        list_collections: CollectionLister,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
        read_interval: IntervalReader = _unset_interval,
        lock: asyncio.Lock | None = None,
        runs: UpkeepRunRegistry = UPKEEP_RUNS,
    ) -> None:
        self._service = service
        self._tidy = tidy
        self._is_enabled = is_enabled
        self._list_collections = list_collections
        self._start_delay_s = start_delay_s
        self._interval_s = interval_s
        self._read_interval = read_interval
        # The vault-write lock a converge round also takes (spec vault-sync
        # ``## Unattended rewriters``): a pass and a round both rewrite vault
        # content, and an export taken half-way through a rewrite is a torn
        # snapshot that git reads as a deliberate change. None on a vault with
        # no sync wired, where there is nothing to interleave with.
        self._lock = lock
        # The same table the button's route claims against. The lock above is
        # vault-wide; this one is per-collection, which is the collision this
        # worker actually has with a person pressing Tidy — see ``_sweep``.
        self._runs = runs

    async def run_forever(self) -> None:
        await asyncio.sleep(self._start_delay_s)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed sweep must never end the loop: the next one is
                # a fresh attempt over the same idempotent pass.
                logger.warning("knowledge.tidy_worker.sweep_failed", exc_info=True)
            # The operator's interval is re-read as the wait runs, so a change
            # in Settings lands within a slice rather than at the end of a wait
            # this worker committed to hours ago.
            await wait_for_next_pass(self._read_interval, default_s=self._interval_s)

    async def run_once(self) -> None:
        """One sweep over every collection, or nothing at all when disabled."""
        if not await self._is_enabled():
            return
        if self._lock is None:
            await self._sweep()
            return
        async with self._lock:
            await self._sweep()

    async def _sweep(self) -> None:
        for collection in await self._list_collections():
            try:
                # Skip, never queue: a collection someone is already tidying by
                # hand does not need a second pass behind the first, and the
                # next sweep comes round to it anyway. Busy is an ordinary
                # state of a collection, so it is not logged as a failure.
                async with self._runs.claimed(KIND_KNOWLEDGE, collection) as claimed:
                    if not claimed:
                        logger.debug(
                            "knowledge.tidy_worker.collection_busy",
                            extra={"collection": collection},
                        )
                        continue
                    await self._tidy(self._service, collection, actor="system")
            except asyncio.CancelledError:
                raise
            except Exception:
                # One collection failing must not skip the rest.
                logger.warning(
                    "knowledge.tidy_worker.collection_failed",
                    extra={"collection": collection},
                    exc_info=True,
                )
