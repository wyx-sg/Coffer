"""Background retention prune worker."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coffer.application.retention_service import RetentionService

_DEFAULT_INTERVAL_SECONDS = 6 * 3600
_logger = logging.getLogger(__name__)


class RetentionWorker:
    """Periodically calls RetentionService.prune.

    Runs immediately on start (catch-up), then every `interval_seconds`.
    Exceptions raised by prune are logged but do not kill the worker.
    """

    def __init__(
        self,
        service: RetentionService,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._service = service
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Run until stop() is called."""
        while not self._stop.is_set():
            await self._safe_prune()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _safe_prune(self) -> None:
        try:
            result = await self._service.prune()
            _logger.info("retention.prune.done", extra={"result": result})
        except Exception:
            _logger.exception("retention.prune.failed")
