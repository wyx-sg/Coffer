"""The background worker that runs the organise pass on an interval.

Shaped like ``knowledge.tidy_worker.TidyWorker``: one catch-up pass shortly
after boot, then on an interval; a failing pass is logged and never kills the
loop; a pending pass never blocks shutdown, because the next boot sweeps
every partition again regardless.

Unlike ``TidyWorker`` — off unless the operator switches it on, because it
rewrites a human's own files with no diff to approve — this worker MAY
default to on. Organise only ever rewrites the derived tree under
``~/.coffer/memory/`` (a digest, and a fact's own status/supersession/conflict
metadata; never a body, never a delete — ``organise.py``'s module docstring),
and that tree is disposable by construction: a bad pass costs nothing worse
than the next sync recomputing it. There is no unattended-rewrite risk here
to be cautious about, so ``is_enabled`` defaults to "always" rather than
requiring an explicit opt-in.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS, UpkeepRunRegistry

logger = logging.getLogger(__name__)

#: Long enough that a boot storm (aggregation, other workers) has settled.
DEFAULT_START_DELAY_S = 60.0
DEFAULT_INTERVAL_S = 6 * 60 * 60.0

OrganiseCallable = Callable[..., Awaitable[object]]
EnabledCheck = Callable[[], Awaitable[bool]]
PartitionLister = Callable[[], Awaitable[list[str]]]


async def _always_enabled() -> bool:
    return True


class OrganiseWorker:
    def __init__(
        self,
        *,
        organise: OrganiseCallable,
        list_partitions: PartitionLister,
        is_enabled: EnabledCheck = _always_enabled,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
        runs: UpkeepRunRegistry = UPKEEP_RUNS,
    ) -> None:
        self._organise = organise
        self._list_partitions = list_partitions
        self._is_enabled = is_enabled
        self._start_delay_s = start_delay_s
        self._interval_s = interval_s
        # The same table the button's route claims against. A timer pass and a
        # button pass over one partition are two writers over one directory,
        # so whichever gets there first holds the key and the other stands
        # down — see ``run_once``.
        self._runs = runs

    async def run_forever(self) -> None:
        await asyncio.sleep(self._start_delay_s)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed sweep must never end the loop: the next one is a
                # fresh attempt over the same idempotent, derived tree.
                logger.warning("memory.organise_worker.sweep_failed", exc_info=True)
            await asyncio.sleep(self._interval_s)

    async def run_once(self) -> None:
        """One sweep over every partition, or nothing at all when disabled."""
        if not await self._is_enabled():
            return
        for partition in await self._list_partitions():
            try:
                # Skip, never queue: a partition someone is already organising
                # by hand does not need a second pass behind the first, and the
                # next sweep comes round to it anyway. Busy is an ordinary
                # state of a partition, so it is not logged as a failure.
                async with self._runs.claimed(KIND_MEMORY, partition) as claimed:
                    if not claimed:
                        logger.debug(
                            "memory.organise_worker.partition_busy",
                            extra={"partition": partition},
                        )
                        continue
                    await self._organise(partition)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One partition failing must not skip the rest.
                logger.warning(
                    "memory.organise_worker.partition_failed",
                    extra={"partition": partition},
                    exc_info=True,
                )


__all__ = [
    "DEFAULT_INTERVAL_S",
    "DEFAULT_START_DELAY_S",
    "OrganiseCallable",
    "OrganiseWorker",
]
