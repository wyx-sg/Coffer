"""Background backup worker."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Protocol

from coffer.domain.sync.backup import DEFAULT_INTERVAL_SECONDS

if TYPE_CHECKING:
    from coffer.domain.sync.backup import BackupRemote, BackupRun

_logger = logging.getLogger(__name__)


class _BackupRunner(Protocol):
    """The slice of ``BackupService`` this worker drives.

    Named structurally rather than imported so the worker — and its test —
    depend on two methods instead of on the service's whole dependency graph.
    """

    async def get(self) -> BackupRemote | None: ...

    async def run_once(self) -> BackupRun: ...


class BackupWorker:
    """Periodically calls BackupService.run_once.

    Runs immediately on start (catch-up), then every `interval_seconds`.
    Exceptions raised by a run are logged but do not kill the worker: a remote
    that is unreachable this hour must not cost the daemon its backups for the
    rest of its life.
    """

    def __init__(
        self,
        service: _BackupRunner,
        *,
        interval_seconds: float | None = None,
    ) -> None:
        self._service = service
        # ``None`` = follow the configured remote. The interval is a UI field,
        # so it is re-read each tick rather than captured at construction; a
        # user who shortens it should not have to restart the daemon to be
        # believed. A number pins the cadence, which is what tests want.
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Run until stop() is called."""
        while not self._stop.is_set():
            await self._safe_run()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=await self._next_interval())
            except TimeoutError:
                continue

    async def _safe_run(self) -> None:
        try:
            run = await self._service.run_once()
            _logger.info(
                "sync.backup.done",
                extra={"status": str(run.status), "commit": run.commit},
            )
        except Exception:
            _logger.exception("sync.backup.failed")

    async def _next_interval(self) -> float:
        if self._interval is not None:
            return self._interval
        try:
            remote = await self._service.get()
        except Exception:
            _logger.exception("sync.backup.interval.failed")
            return float(DEFAULT_INTERVAL_SECONDS)
        # No remote configured is the ordinary state of a fresh install: the
        # loop keeps ticking on the default cadence so configuring a remote
        # takes effect on its own, without a restart.
        if remote is None:
            return float(DEFAULT_INTERVAL_SECONDS)
        return float(remote.interval_seconds)
