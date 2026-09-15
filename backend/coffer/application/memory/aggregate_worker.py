"""The background worker that re-aggregates the agents' native memory.

Spec memory FR-007: aggregation MUST run on a worker on an interval and MUST
also be triggerable by hand. It ran only by hand for its whole first life —
the Memory page's Sync button and `coffer memory sync` — which made a layer
whose entire premise is "what your agents already learned is here" quietly
depend on the user remembering to ask. A fact learned this morning was not in
Coffer until someone clicked.

Shaped like ``organise_worker.OrganiseWorker``, and on for the same reason:
a pass only *reads* the agents' own files and only *writes* the derived tree
under ``~/.coffer/memory/`` (FR-023 — deleting that tree and re-running
reproduces it), so there is no unattended-write risk to gate behind an
operator switch. It is also cheap to repeat: FR-006 skips any source file
whose content hash is unchanged, so a pass over an idle machine parses
nothing.

Unlike the organise sweep this one runs a catch-up pass **on start**, not
after a delay. Aggregation is what fills the layer, and a daemon that has
just started is exactly when its picture of the agents is most stale.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

#: Frequent enough that a fact an agent learned this morning is here by the
#: afternoon; rare enough that an idle machine's passes cost a stat per source.
DEFAULT_INTERVAL_S = 60 * 60.0

AggregateCallable = Callable[..., Awaitable[object]]

#: The actor recorded on an unattended pass's audit event, so the log can tell
#: a scheduled aggregation apart from one the user asked for (FR-063).
WORKER_ACTOR = "system:memory-aggregate-worker"


class AggregateWorker:
    """Runs one aggregation pass on start, then every ``interval_s``."""

    def __init__(
        self,
        *,
        aggregate: AggregateCallable,
        interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        self._aggregate = aggregate
        self._interval_s = interval_s

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
            await asyncio.sleep(self._interval_s)

    async def run_once(self) -> None:
        """One aggregation pass over every registered, enabled agent."""
        await self._aggregate(actor=WORKER_ACTOR)


__all__ = [
    "DEFAULT_INTERVAL_S",
    "WORKER_ACTOR",
    "AggregateCallable",
    "AggregateWorker",
]
