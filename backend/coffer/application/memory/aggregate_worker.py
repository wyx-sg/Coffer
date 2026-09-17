"""The background worker that re-aggregates the agents' native memory.

Spec memory FR-007: aggregation MUST run on a worker on an interval and MUST
also be triggerable by hand. It ran only by hand for its whole first life —
the Memory page's Sync button and `coffer memory sync` — which made a layer
whose entire premise is "what your agents already learned is here" quietly
depend on the user remembering to ask. A lesson an agent recorded this morning
was not in Coffer until someone clicked.

Shaped like the distil sweep's worker, and on for the same reason: a pass only
*reads* the agents' own files and only *writes* the derived tree under
``~/.coffer/memory/`` (FR-019 — deleting that tree and re-running reproduces an
equivalent one), so there is no unattended-write risk to gate behind an
operator switch. It is also cheap to repeat: FR-006 skips any source file whose
content hash is unchanged, so a pass over an idle machine parses nothing and
writes nothing.

Unlike the distil sweep this one runs a catch-up pass **on start**, not after a
delay. Aggregation is what fills the layer, and a daemon that has just started
is exactly when its picture of the agents is most stale.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.upkeep_schedule import IntervalReader, wait_for_next_pass

logger = logging.getLogger(__name__)

#: Frequent enough that a lesson an agent recorded this morning is here by the
#: afternoon; rare enough that an idle machine's passes cost a hash per source.
DEFAULT_INTERVAL_S = 60 * 60.0

AggregateCallable = Callable[..., Awaitable[object]]
EnabledCheck = Callable[[], Awaitable[bool]]


async def _always_enabled() -> bool:
    return True


async def _unset_interval() -> int | None:
    """No interval chosen — the constant above applies. The composition root
    injects a reader of the operator's setting instead."""
    return None


#: The actor recorded on an unattended pass's audit event, so the log can tell
#: a scheduled aggregation apart from one the user asked for (FR-038).
WORKER_ACTOR = "system:memory-aggregate-worker"


class AggregateWorker:
    """Runs one aggregation pass on start, then every ``interval_s``."""

    def __init__(
        self,
        *,
        aggregate: AggregateCallable,
        is_enabled: EnabledCheck = _always_enabled,
        interval_s: float = DEFAULT_INTERVAL_S,
        read_interval: IntervalReader = _unset_interval,
    ) -> None:
        self._aggregate = aggregate
        self._is_enabled = is_enabled
        self._interval_s = interval_s
        self._read_interval = read_interval

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed pass must never end the loop. Aggregation is
                # idempotent over a derived tree, so the next one is simply a
                # fresh attempt — and FR-005 already isolates one unreadable
                # agent from the rest.
                logger.warning("memory.aggregate_worker.pass_failed", exc_info=True)
            # The operator's interval is re-read as the wait runs, so changing
            # it in Settings takes effect within a slice rather than an hour.
            await wait_for_next_pass(self._read_interval, default_s=self._interval_s)

    async def run_once(self) -> None:
        """One aggregation pass over every registered, enabled agent, or
        nothing at all when the operator has switched this pass off."""
        if not await self._is_enabled():
            return
        await self._aggregate(actor=WORKER_ACTOR)


__all__ = [
    "DEFAULT_INTERVAL_S",
    "WORKER_ACTOR",
    "AggregateCallable",
    "AggregateWorker",
    "EnabledCheck",
]
