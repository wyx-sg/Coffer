"""How long Coffer waits for its own model on one call (spec internal-engine FR-022).

Every call Coffer's internal engine makes is bounded, because an unbounded one
is how an unattended pass stops being unattended: a wedged endpoint that never
answers leaves the pass holding a connection until the daemon is restarted, and
nothing in the UI says so. The bound used to be a constant compiled into each
call site — 60 seconds in the distil pass, 20 in knowledge ingestion, none at
all on curation's turns.

**Why it had to become a setting.** The right number is a property of the
operator's endpoint, not of Coffer. Measured against a gateway whose typical
answer takes 25-30 seconds, a 60-second bound leaves barely a factor of two,
and the passes then fail in the least useful way available to them: the failure
is graceful — a timed-out routing chunk simply defers its entries to the next
pass (see :mod:`coffer.application.memory.distil`) — so nothing breaks, nothing
is lost, and the layer merely converges at a fraction of the rate it should
while reporting success. A knob that needs a rebuild to turn is not a knob.

**Read per call, never captured.** Like ``upkeep_schedule``'s interval, and for
the same reason: the value is a singleton the operator may change from this
machine's Settings page or from another machine's (the row converges through
vault sync), and a value read once at wiring time would hold until a restart.

**``None`` means the default**, which keeps the default in one place — here —
so raising it later reaches every vault that never chose, rather than none of
them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

#: The bound that applies while the operator has chosen none. Sixty seconds is
#: what every call site carried before this module existed; it is kept as the
#: default so making the number configurable changes no vault's behaviour on
#: its own.
DEFAULT_MODEL_TIMEOUT_S = 60.0

#: The floor is not politeness — below it the bound would expire before a
#: healthy endpoint could answer, turning every pass into a no-op that looks
#: like a broken model. The ceiling bounds the damage a typo does: an
#: unattended pass that holds a wedged connection for an hour is the failure
#: this module exists to prevent, and a five-digit timeout would reintroduce it.
MIN_MODEL_TIMEOUT_S = 5
MAX_MODEL_TIMEOUT_S = 600

#: Reads the currently configured bound in seconds, or ``None`` for the
#: default. ``None`` in place of the reader itself means the caller has no
#: settings to consult — a unit test, or a pass constructed before the
#: singleton exists — and gets the default too.
TimeoutReader = Callable[[], Awaitable[int | None]]


async def resolve_timeout(read: TimeoutReader | None) -> float:
    """The bound one model call should use, right now.

    Out-of-range values are clamped rather than raised on. The surfaces refuse
    them on the way in, so a value out here came from a row written by an older
    build or edited by hand in a synced document — and a background pass is the
    wrong place to discover it, where raising would take down a pass that could
    have run.
    """
    if read is None:
        return DEFAULT_MODEL_TIMEOUT_S
    chosen = await read()
    if chosen is None:
        return DEFAULT_MODEL_TIMEOUT_S
    return float(min(max(chosen, MIN_MODEL_TIMEOUT_S), MAX_MODEL_TIMEOUT_S))


__all__ = [
    "DEFAULT_MODEL_TIMEOUT_S",
    "MAX_MODEL_TIMEOUT_S",
    "MIN_MODEL_TIMEOUT_S",
    "TimeoutReader",
    "resolve_timeout",
]
