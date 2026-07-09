"""Opt-in auto-sync worker: near-real-time convergence (spec 010, ADR-043).

While ``config.auto`` is on and a remote is configured, three signals schedule
a full sync run:

- **Local changes** (``notify_change()`` — resource mutations and file-tree
  watcher events): debounced by a quiet period, capped so a steady stream of
  changes still syncs.
- **Remote movement**: a ``git ls-remote`` head probe every
  ``poll_remote_seconds``; a run fires only when the head differs from the one
  this machine last converged on.
- **Fallback sweep**: the fixed ``interval_seconds``, which also catches
  anything missed while triggers were suppressed during a run (the import's
  own writes must not re-fire the watcher into an endless run loop).

Failures never kill the loop — the service records them as the sync ``error``
state and the loop retries on the next signal. Off by default; the task is
always running but does nothing until ``auto`` is enabled.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import structlog

from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.ports import GitPort
from coffer.application.sync.service import SyncService
from coffer.domain.sync.errors import SyncInProgress
from coffer.domain.sync.models import SyncConfig

_log = structlog.get_logger(__name__)

#: How often the loop wakes to evaluate the three signals.
_TICK_SECONDS = 1.0

#: Quiet period after the last local change before a run fires.
DEBOUNCE_SECONDS = 5.0

#: A steady stream of changes still syncs at most this long after the first.
DEBOUNCE_CAP_SECONDS = 30.0


class SyncWorker:
    def __init__(
        self,
        service: SyncService,
        config: SyncConfigService,
        git: GitPort | None = None,
        *,
        poll_seconds: float = _TICK_SECONDS,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        debounce_cap_seconds: float = DEBOUNCE_CAP_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._service = service
        self._config = config
        self._git = git
        self._poll = poll_seconds
        self._debounce = debounce_seconds
        self._debounce_cap = debounce_cap_seconds
        self._clock = clock
        self._stop = asyncio.Event()
        self._first_change: float | None = None
        self._last_change: float | None = None
        self._suppress = False
        self._last_run: float | None = None
        self._last_remote_poll: float | None = None
        self._last_seen_head: str | None = None

    def stop(self) -> None:
        self._stop.set()

    def notify_change(self) -> None:
        """Record a local change.

        Events raised while a run is in flight are dropped — the import's own
        tree writes and resource mutations would otherwise re-fire forever
        (this covers manual runs too, via the service lock); the fallback
        sweep covers genuine changes made during a run."""
        if self._suppress or self._service.is_running:
            return
        now = self._clock()
        if self._first_change is None:
            self._first_change = now
        self._last_change = now

    async def run(self) -> None:
        while not self._stop.is_set():
            await self._maybe_sync()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except TimeoutError:
                continue

    # --- internals -----------------------------------------------------------

    async def _maybe_sync(self) -> None:
        try:
            config = await self._config.get_config()
            if not (config.auto and config.is_operational()):
                self._first_change = self._last_change = None
                return
            now = self._clock()
            due = self._change_due(now) or await self._remote_moved(config, now)
            if not due and (
                self._last_run is None or now - self._last_run >= config.interval_seconds
            ):
                due = True  # fallback sweep
            if not due:
                return
            self._first_change = self._last_change = None
            self._last_run = now
            self._suppress = True
            try:
                await self._service.run()
            finally:
                self._suppress = False
            # Our own push moved the remote head; remember it so the next
            # probe doesn't schedule a pointless run.
            if self._git is not None:
                self._last_seen_head = await asyncio.to_thread(self._git.head)
        except SyncInProgress:
            return
        except Exception as e:  # never let the loop die
            _log.warning("auto_sync_failed", error=str(e))

    def _change_due(self, now: float) -> bool:
        if self._first_change is None or self._last_change is None:
            return False
        quiet = now - self._last_change >= self._debounce
        capped = now - self._first_change >= self._debounce_cap
        return quiet or capped

    async def _remote_moved(self, config: SyncConfig, now: float) -> bool:
        if self._git is None or config.remote is None:
            return False
        if (
            self._last_remote_poll is not None
            and now - self._last_remote_poll < config.poll_remote_seconds
        ):
            return False
        self._last_remote_poll = now
        head = await asyncio.to_thread(self._git.remote_head, config.remote, config.branch)
        if head is None:
            return False
        if self._last_seen_head is None:
            # First observation: startup convergence comes from the immediate
            # fallback sweep (last_run is None), not a duplicate probe-run.
            self._last_seen_head = head
            return False
        if head == self._last_seen_head:
            return False
        self._last_seen_head = head
        return True
