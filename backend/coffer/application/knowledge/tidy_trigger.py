"""What arms the notes tidy pass — on idle after writes, and on an interval.

The tidy pass itself is :class:`~coffer.application.knowledge.reorg.ReorgService`:
a bounded agentic loop that merges duplicate notes and rewrites them into
coherent topic documents, archiving each replaced revision under
``<scope>/.history/`` first. This module decides *when* it runs.

Two arming paths, one component, because they cover different gaps:

* **On idle.** Every write re-arms a single coalescing timer; after a quiet
  spell the scopes that changed are tidied. This is what makes the pass feel
  like "it tidies up after a session ends".
* **On an interval.** A periodic sweep over every scope, modelled on the
  sibling ``RetentionWorker``: one catch-up pass at boot, then every
  ``interval_seconds``. This catches what the idle timer structurally cannot —
  files a user edited in their own editor, a daemon restarted before its timer
  fired, and a scope nothing has written to in a while.

Both paths call the same entry point, and neither serializes against the other
or against a concurrent ``coffer__write``: the pass reconciles under the store
lock but does its own note writes outside it, and the lock is not reentrant, so
wrapping the pass in it would deadlock on the reconcile it already performs.
What makes the interleaving safe is not exclusion but the archive — the pass
only ever deletes notes it read and merged, and every delete and overwrite
moves the prior revision into ``.history/`` first, so a write that lands
mid-pass is recoverable rather than lost.

A failure is logged and never propagates: neither path may take down the daemon
or stop future passes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)

#: A quiet spell this long after a write reads as "the session moved on".
_DEFAULT_IDLE_DELAY_SECONDS = 300.0
#: How often the sweep revisits every scope. Deliberately unhurried: the pass
#: costs LLM calls, and nothing about a tidy is urgent.
_DEFAULT_INTERVAL_SECONDS = 6 * 3600


class TidyPort(Protocol):
    """The tidy pass, as this module needs it."""

    async def reorg(self, *, scope_name: str) -> Any: ...


#: ``() -> [scope name, ...]`` — every scope the sweep should visit.
ListScopesFn = Callable[[], Awaitable[list[str]]]


class NotesTidyTrigger:
    """Arms the notes tidy pass on idle and on an interval."""

    def __init__(
        self,
        *,
        tidy: TidyPort,
        list_scopes: ListScopesFn,
        idle_delay_seconds: float = _DEFAULT_IDLE_DELAY_SECONDS,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._tidy = tidy
        self._list_scopes = list_scopes
        self._idle_delay = idle_delay_seconds
        self._interval = interval_seconds
        self._dirty: set[str] = set()
        self._idle_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # --- the idle path ------------------------------------------------------

    async def on_change(self, scope_name: str) -> None:
        """Re-arm the idle timer. Wired to ``KnowledgeService.set_on_change``."""
        self._dirty.add(scope_name)
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()  # re-arm; the dirty set is preserved
        self._idle_task = asyncio.create_task(self._tidy_after_idle())

    async def _tidy_after_idle(self) -> None:
        try:
            await asyncio.sleep(self._idle_delay)
        except asyncio.CancelledError:
            return  # re-armed or shutting down; a newer timer owns the dirty set
        scopes = sorted(self._dirty)
        self._dirty.clear()
        for name in scopes:
            await self._tidy_one(name)

    # --- the interval path --------------------------------------------------

    async def run(self) -> None:
        """The periodic sweep. Runs until :meth:`stop` is called."""
        while not self._stop.is_set():
            await self._sweep()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)

    def stop(self) -> None:
        """Signal the sweep loop to exit cleanly."""
        self._stop.set()

    async def _sweep(self) -> None:
        try:
            scopes = await self._list_scopes()
        except Exception:
            logger.warning("knowledge.tidy.sweep_list_failed", exc_info=True)
            return
        for name in scopes:
            if self._stop.is_set():
                return
            await self._tidy_one(name)

    # --- shared -------------------------------------------------------------

    async def _tidy_one(self, scope_name: str) -> None:
        """One scope, best-effort. A failure never reaches the caller."""
        try:
            await self._tidy.reorg(scope_name=scope_name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "knowledge.tidy.failed",
                extra={"scope": scope_name},
                exc_info=True,
            )

    async def shutdown(self) -> None:
        """Stop the sweep and drop a pending idle timer WITHOUT firing it.

        Nothing is lost by not firing: the pass is idempotent, and the next
        boot's catch-up sweep visits every scope anyway.
        """
        self.stop()
        task, self._idle_task = self._idle_task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


__all__ = ["ListScopesFn", "NotesTidyTrigger", "TidyPort"]
