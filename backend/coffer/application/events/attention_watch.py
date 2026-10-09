"""Announce a change in what the attention list reports.

The attention list has no write of its own — it is computed on demand from
each kind's source — so nothing would otherwise tell the event stream it
moved. The watcher recomputes a fingerprint of the report:

- after resource writes, once they settle (a burst costs one recompute);
- after every writing reconcile pass, since drift the pass repaired or left
  open is what the drift source reports;
- on a slow period, for signals no write or pass announces (a launcher
  installed, a health row a test wrote).

When the fingerprint differs from the last one it publishes one ``attention``
envelope with no id and no revision; the first computation only sets the
baseline. The envelope carries no item: a client refetches the list.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Hashable

from coffer.application.attention import AttentionReport
from coffer.application.events.broker import EventBroker
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.domain.reconcile import Changed, PassReport

_log = logging.getLogger(__name__)

#: The envelope kind a change in the attention list is announced under.
ATTENTION_KIND = "attention"
#: How long a nudge waits for its neighbours before recomputing.
DEFAULT_SETTLE_SECONDS = 0.5
#: How often the list is recomputed with nothing prompting it.
DEFAULT_PERIOD_SECONDS = 30.0

ReportFn = Callable[[], Awaitable[AttentionReport]]


def fingerprint(report: AttentionReport) -> Hashable:
    """What a person would see change: which items are listed, why and how
    urgently, and which sources failed. Titles, reasons' wording, times and
    error texts are left out — they may vary without the list meaning
    anything different."""
    items = frozenset((i.kind, i.uid, i.reason_code, i.severity.value) for i in report.items)
    errors = frozenset(e.source for e in report.errors)
    return (items, errors)


class AttentionWatcher:
    """Publishes an ``attention`` envelope whenever the fingerprint moves."""

    def __init__(
        self,
        broker: EventBroker,
        *,
        settle_seconds: float = DEFAULT_SETTLE_SECONDS,
        period_seconds: float = DEFAULT_PERIOD_SECONDS,
    ) -> None:
        self._broker = broker
        self._loop = WakeableLoop(
            "attention-watch",
            self._run_once,
            fallback=period_seconds,
            settle=settle_seconds,
            failure_event="events.attention_check_failed",
        )
        self._report: ReportFn | None = None
        self._last: Hashable | None = None
        #: Called on every nudge, so whoever keeps the last report drops it at once.
        self.on_nudge: Callable[[], None] | None = None

    # --- nudges (sync, never block) ---------------------------------------------

    def nudge(self) -> None:
        """Recompute soon."""
        if self.on_nudge is not None:
            self.on_nudge()
        self._loop.poke()

    def on_changed(self, changed: Changed) -> None:
        """A resource write (a ``HintSink``)."""
        self.nudge()

    def on_pass(self, report: PassReport) -> None:
        """A writing reconcile pass finished (a ``PassListener``)."""
        self.nudge()

    # --- computing ----------------------------------------------------------------

    async def check(self, report: ReportFn) -> bool:
        """Recompute now; publish and return ``True`` when the list moved.
        The first call only records the baseline."""
        current = fingerprint(await report())
        moved = self._last is not None and current != self._last
        self._last = current
        if moved:
            self._broker.publish(ATTENTION_KIND, None, "upsert")
        return moved

    async def prime(self, report: ReportFn) -> None:
        """Record the baseline now; a failure is logged, never raised, and
        :meth:`serve` tries again."""
        await self._check_logged(report)

    async def serve(self, report: ReportFn) -> None:
        """Set the baseline if unset, then recompute on every settled nudge
        and every period until cancelled. A failed recompute is logged and
        the loop carries on."""
        self._report = report
        if self._last is None:
            await self._check_logged(report)
        await self._loop.serve()

    async def _run_once(self, _poked: bool) -> None:
        if self._report is not None:
            await self.check(self._report)

    async def _check_logged(self, report: ReportFn) -> None:
        try:
            await self.check(report)
        except Exception:
            _log.exception("events.attention_check_failed")


__all__ = [
    "ATTENTION_KIND",
    "DEFAULT_PERIOD_SECONDS",
    "DEFAULT_SETTLE_SECONDS",
    "AttentionWatcher",
    "ReportFn",
    "fingerprint",
]
