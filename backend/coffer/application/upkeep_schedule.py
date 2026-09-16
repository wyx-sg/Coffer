"""Waiting for the next unattended pass, in a way a settings change can reach.

Coffer runs three passes on its own behalf — aggregation, organise, tidy — and
each one used to wait with a single ``asyncio.sleep(interval)`` over a constant
compiled into the worker. Both halves of that are now the operator's to choose
(spec memory FR-007, spec knowledge FR-051), and a long sleep is exactly how a
choice goes unnoticed: a worker that went to sleep for six hours does not learn
that the interval is now fifteen minutes until the six hours are up, so the
setting appears not to work at all for most of a day.

So the wait is taken in slices and the interval is re-read each slice. The
pass's own default applies while the operator has chosen nothing (``None``),
which keeps that default in the worker that owns the pass rather than copied
into every vault — raising it later then reaches every vault that never chose.

The slice is the resolution of the whole mechanism: a change lands within one
of them, and a pass never starts more than one slice late. It is a plain sleep
rather than an event the settings write fires, because the settings write is
in a different process on a different machine as often as it is in this one
(the singleton converges through vault sync), and there is no event to fire
from over there.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from coffer.domain.internal_engine_config import AGGREGATE, ORGANISE, TIDY

#: How often the wait looks up again. Short enough that changing an interval in
#: Settings visibly takes effect, long enough to be free.
SLICE_S = 30.0


#: Each pass's own interval, used while the operator has chosen none. They live
#: together here rather than one per worker so the surface that OFFERS the
#: setting can label "default" with the real number without importing three
#: kind-specific modules — a kind-agnostic module must not, and a settings page
#: showing a blank where the default belongs is the alternative.
DEFAULT_INTERVALS: dict[str, float] = {
    # Frequent enough that a fact an agent learned this morning is here by the
    # afternoon; rare enough that an idle machine's passes cost a stat per source.
    AGGREGATE: 60 * 60.0,
    # Both model passes are slower and rewrite more, so they sweep four times a
    # day rather than hourly.
    ORGANISE: 6 * 60 * 60.0,
    TIDY: 6 * 60 * 60.0,
}


#: Reads the pass's currently configured interval in seconds, or ``None`` for
#: "whatever this pass's default is".
IntervalReader = Callable[[], Awaitable[int | None]]


async def wait_for_next_pass(
    read_interval: IntervalReader,
    *,
    default_s: float,
    slice_s: float = SLICE_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Sleep until this pass is due, honouring an interval changed mid-wait.

    Elapsed time is counted against the interval as it stands *now*, so
    shortening the interval can make a pass due immediately — which is what the
    operator asked for by shortening it — and lengthening it extends the wait
    already in progress rather than taking effect only from the pass after next.
    """
    waited = 0.0
    while True:
        interval = await read_interval()
        due_at = float(interval) if interval and interval > 0 else default_s
        if waited >= due_at:
            # Always yield at least once, even for a zero interval. A caller's
            # loop is `pass; wait; pass; …`, so returning without ever handing
            # control back would not be a fast timer — it would be a loop that
            # never lets the daemon serve a request again.
            if waited == 0.0:
                await sleep(0)
            return
        nap = min(slice_s, due_at - waited)
        await sleep(nap)
        waited += nap


__all__ = ["DEFAULT_INTERVALS", "SLICE_S", "IntervalReader", "wait_for_next_pass"]
