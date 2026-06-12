"""Opt-in auto-sync worker (spec 010).

Modeled on the retention worker: a daemon background task that, while
``config.auto`` is on and a remote is configured, runs a full sync at the
configured interval. A run pushes local changes and pulls/imports others, so two
machines with auto-sync on converge without any manual command. Off by default;
the task is always running but does nothing until ``auto`` is enabled.

Failures (network, git) never kill the loop — they are recorded as the sync
``error`` state by the service and the loop retries on the next tick.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.service import SyncService
from coffer.domain.sync.errors import SyncInProgress

_log = structlog.get_logger(__name__)

#: How often the loop wakes to check whether a run is due / auto was toggled.
_POLL_SECONDS = 5.0


class SyncWorker:
    def __init__(
        self,
        service: SyncService,
        config: SyncConfigService,
        *,
        poll_seconds: float = _POLL_SECONDS,
    ) -> None:
        self._service = service
        self._config = config
        self._poll = poll_seconds
        self._stop = asyncio.Event()
        self._last_run: float | None = None

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            await self._maybe_sync()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except TimeoutError:
                continue

    async def _maybe_sync(self) -> None:
        try:
            config = await self._config.get_config()
            if not (config.auto and config.is_operational()):
                return
            now = time.monotonic()
            if self._last_run is not None and now - self._last_run < config.interval_seconds:
                return
            self._last_run = now
            await self._service.run()
        except SyncInProgress:
            return
        except Exception as e:  # never let the loop die
            _log.warning("auto_sync_failed", error=str(e))
