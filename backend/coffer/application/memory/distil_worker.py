"""The background worker that runs the distil pass on an interval (FR-007).

Shaped like ``aggregate_worker.AggregateWorker``: a catch-up pass shortly after
boot, then on an interval; a failing pass is logged and never kills the loop; a
pending pass never blocks shutdown, because the next boot sweeps every
partition again regardless. The switch and the interval are read **per tick**,
not at boot, so an operator who turns the pass off or shortens its interval in
Settings does not have to restart the daemon to be obeyed (spec
provider-switching E3a).

The delay before the first pass is the one difference from aggregation, and it
is deliberate: aggregation is what *fills* ``.raw/``, and distilling a
partition before this boot's aggregation has run would spend a model on the
same entries the pass a minute later would have seen anyway.

**On by default**, like aggregation and unlike knowledge's tidy. Tidy is off
until the operator switches it on because it rewrites the human's own files
with no diff to approve. Everything this pass writes is under
``~/.coffer/memory/``, which is derived by construction (FR-019): delete it,
run aggregation and distil, and an equivalent partition comes back. There is no
unattended-rewrite risk here to gate behind consent — only a model call, which
is what the switch is actually for.

**One pass per partition, whoever started it (FR-041).** The timer and the
Distil button are two writers over one directory, so both claim the same
upkeep-runs key: whichever arrives first holds it, the button's route is
refused with ``UPKEEP_ALREADY_RUNNING`` and this worker simply skips the
partition. Busy is an ordinary state of a partition, not a failure, so it is
logged at debug and the next sweep comes round to it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS, UpkeepRunRegistry
from coffer.application.upkeep_schedule import IntervalReader, wait_for_next_pass

logger = logging.getLogger(__name__)

#: Long enough that the boot storm — this daemon's first aggregation above all
#: — has settled before a model is spent on what it found.
DEFAULT_START_DELAY_S = 60.0
#: Slower than aggregation's hour: this pass calls a model and rewrites notes,
#: where aggregation skips every source whose digest is unchanged.
DEFAULT_INTERVAL_S = 6 * 60 * 60.0

#: The actor recorded on an unattended pass's audit event, so the log can tell
#: a scheduled distillation apart from one the user asked for (FR-038).
WORKER_ACTOR = "system:memory-distil-worker"

DistilCallable = Callable[..., Awaitable[object]]
EnabledCheck = Callable[[], Awaitable[bool]]
#: Yields the **uids** of the partitions to sweep. A pass spends a model and
#: rewrites every note in a directory, so it is aimed at the identity rather
#: than at a label the user can edit while it runs — and the Distil button
#: sends the same uid, which is what lets the claim below and the route's claim
#: collide the way FR-041 needs them to without either side translating.
PartitionLister = Callable[[], Awaitable[list[str]]]


async def _always_enabled() -> bool:
    return True


async def _unset_interval() -> int | None:
    """No interval chosen — the constant above applies. The composition root
    injects a reader of the operator's setting instead."""
    return None


class DistilWorker:
    """Sweeps every partition through the distil pass, on a timer."""

    def __init__(
        self,
        *,
        distil: DistilCallable,
        list_partitions: PartitionLister,
        is_enabled: EnabledCheck = _always_enabled,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
        read_interval: IntervalReader = _unset_interval,
        runs: UpkeepRunRegistry = UPKEEP_RUNS,
    ) -> None:
        self._distil = distil
        self._list_partitions = list_partitions
        self._is_enabled = is_enabled
        self._start_delay_s = start_delay_s
        self._interval_s = interval_s
        self._read_interval = read_interval
        # The same table the button's route claims against (FR-041).
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
                # fresh attempt over the same idempotent, derived tree — and a
                # pass with no new raw entries does nothing but rewrite an
                # index, so repeating one costs nothing.
                logger.warning("memory.distil_worker.sweep_failed", exc_info=True)
            # Not a plain sleep: the operator's interval is re-read as the wait
            # runs, so shortening it in Settings takes effect now rather than
            # after the six hours this worker had already committed to.
            await wait_for_next_pass(self._read_interval, default_s=self._interval_s)

    async def run_once(self) -> None:
        """One sweep over every partition, or nothing at all when disabled."""
        if not await self._is_enabled():
            return
        for uid in await self._list_partitions():
            try:
                async with self._runs.claimed(KIND_MEMORY, uid) as claimed:
                    if not claimed:
                        logger.debug(
                            "memory.distil_worker.partition_busy",
                            extra={"partition_uid": uid},
                        )
                        continue
                    await self._distil(uid)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One partition failing must not skip the rest.
                logger.warning(
                    "memory.distil_worker.partition_failed",
                    extra={"partition_uid": uid},
                    exc_info=True,
                )


__all__ = [
    "DEFAULT_INTERVAL_S",
    "DEFAULT_START_DELAY_S",
    "WORKER_ACTOR",
    "DistilCallable",
    "DistilWorker",
]
