"""The background worker that runs the tidy pass on an interval.

It is off unless the operator turns it on. That default is the point rather
than caution: the pass rewrites files a human and an agent manage together,
with no diff to approve before it lands (spec knowledge FR-051), so an
unattended rewriter should be something the operator switched on, never
something they discover running.

Shaped like ``RetentionWorker``: one catch-up pass shortly after boot, then on
an interval; a failing pass is logged and never kills the loop; a pending pass
never blocks shutdown, because the tidy is idempotent and the next boot sweeps
everything again.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first pass.
DEFAULT_START_DELAY_S = 60.0
DEFAULT_INTERVAL_S = 6 * 60 * 60.0

TidyCallable = Callable[..., Awaitable[dict[str, object]]]
EnabledCheck = Callable[[], Awaitable[bool]]
CollectionLister = Callable[[], Awaitable[list[str]]]


class TidyWorker:
    def __init__(
        self,
        *,
        service: KnowledgeService,
        tidy: TidyCallable,
        is_enabled: EnabledCheck,
        list_collections: CollectionLister,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        self._service = service
        self._tidy = tidy
        self._is_enabled = is_enabled
        self._list_collections = list_collections
        self._start_delay_s = start_delay_s
        self._interval_s = interval_s

    async def run_forever(self) -> None:
        await asyncio.sleep(self._start_delay_s)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed sweep must never end the loop: the next one is
                # a fresh attempt over the same idempotent pass.
                logger.warning("knowledge.tidy_worker.sweep_failed", exc_info=True)
            await asyncio.sleep(self._interval_s)

    async def run_once(self) -> None:
        """One sweep over every collection, or nothing at all when disabled."""
        if not await self._is_enabled():
            return
        for collection in await self._list_collections():
            try:
                await self._tidy(self._service, collection, actor="system")
            except asyncio.CancelledError:
                raise
            except Exception:
                # One collection failing must not skip the rest.
                logger.warning(
                    "knowledge.tidy_worker.collection_failed",
                    extra={"collection": collection},
                    exc_info=True,
                )
