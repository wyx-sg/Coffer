"""One loop for a background worker that sleeps until something needs it.

The reconciler, the attention watch and the vault scanner each wrote the same
loop by hand: wait for a hint or a period, let a burst of hints settle, run once,
log a failure and carry on. :class:`WakeableLoop` is that loop, written once
(ADR background-workers-wake-on-events):

* :meth:`~WakeableLoop.poke` wakes it; pokes that arrive before or during the
  settle are one run.
* ``fallback`` seconds without a poke run it anyway, to catch an event that was
  lost; ``None`` means it waits for a poke only.
* :meth:`~WakeableLoop.set_demand` ``(False)`` parks it with no timer at all,
  until demand comes back.

Each run is reported to :mod:`workers`, so the daemon's status says what every
worker built on it is doing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from coffer.application.runtime.workers import WorkerMode, WorkerRegistry, workers

_log = logging.getLogger(__name__)

#: One run. ``True`` when a poke woke it, ``False`` when the fallback did.
RunOnce = Callable[[bool], Awaitable[object]]


class WakeableLoop:
    """A named worker loop: woken by pokes, a fallback timer, or not at all."""

    def __init__(
        self,
        name: str,
        run_once: RunOnce,
        *,
        fallback: float | None,
        settle: float = 0.0,
        mode: WorkerMode | None = None,
        failure_event: str = "runtime.worker.failed",
        registry: WorkerRegistry | None = None,
    ) -> None:
        self.name = name
        self._run_once = run_once
        self._fallback = fallback
        self._settle = settle
        self._mode = mode or (WorkerMode.EVENT if fallback is None else WorkerMode.EVENT_FALLBACK)
        self._failure_event = failure_event
        self._registry = registry or workers()
        #: Set by a poke, cleared when the run it asked for starts.
        self._poked = False
        self._demand = True
        #: Set by a poke or a change of demand: whatever :meth:`_wait` sleeps on.
        self._stir = asyncio.Event()

    @property
    def fallback(self) -> float | None:
        return self._fallback

    def poke(self) -> None:
        """Something changed: run once, after the settle."""
        self._poked = True
        self._stir.set()

    def set_demand(self, wanted: bool) -> None:
        """Park the loop (no timer, no runs) or bring it back."""
        if wanted != self._demand:
            self._demand = wanted
            self._stir.set()

    async def serve(self) -> None:
        """Run until cancelled. A run that raises is logged and counted."""
        token = self._registry.register(self.name, self._mode)
        try:
            while True:
                poked = await self._wait(token)
                if poked and self._settle:
                    await asyncio.sleep(self._settle)
                self._poked = False
                await self._run(token, poked)
        finally:
            self._registry.drop(self.name, token)

    async def _run(self, token: object, poked: bool) -> None:
        self._registry.started(self.name, token)
        clock = time.monotonic()
        ok = False
        try:
            await self._run_once(poked)
            ok = True
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception(self._failure_event, extra={"worker": self.name})
        finally:
            self._registry.finished(self.name, token, ok=ok, seconds=time.monotonic() - clock)

    async def _wait(self, token: object) -> bool:
        """Until a poke (``True``) or the fallback (``False``), parked meanwhile
        whenever demand is off."""
        while True:
            self._stir.clear()
            if not self._demand:
                self._registry.parked(self.name, token)
                await self._stir.wait()
                continue
            if self._poked:
                # Due once the settle is over.
                self._registry.waiting(self.name, token, self._settle)
                return True
            self._registry.waiting(self.name, token, self._fallback)
            try:
                await asyncio.wait_for(self._stir.wait(), timeout=self._fallback)
            except TimeoutError:
                return False


__all__ = ["RunOnce", "WakeableLoop"]
