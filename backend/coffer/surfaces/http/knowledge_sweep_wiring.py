"""Startup wiring for the knowledge sweep, the one background worker knowledge has.

Every run is :func:`coffer.application.knowledge.sweep.sweep_once`: it promotes
what waits in a collection's ``.inbox/``, commits edits found on disk, and
re-renders the guide skill. All three are mechanical, so the sweep runs on every
machine whenever the ``knowledge`` feature is on (spec experimental-features
"Close every surface of a switched-off feature"): a collection's files are the
same wherever it is read, and what the sweep writes goes through ``VaultWriter``
like any other write.

Kept out of ``app.py`` and ``background_workers.py`` so those stay short,
mirroring the sibling ``*_wiring.py`` modules.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from coffer.application.features import FeatureService
from coffer.application.knowledge.layout import loose_documents_waiting
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.sweep import sweep_once
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.domain.features import KNOWLEDGE
from coffer.infrastructure.knowledge.layout import QUIET_SECONDS
from coffer.surfaces.http.guide_wiring import BuiltinGuide

_log = logging.getLogger(__name__)

#: Seconds without a file event after which the sweep runs anyway, to catch an
#: event the watch lost. A file dropped into an inbox or edited on disk wakes the
#: sweep at once, so this is only the safety net.
SWEEP_FALLBACK_S = 600.0
#: Seconds a burst of file events settles before the sweep runs: a copy of many
#: files is one run.
SWEEP_SETTLE_S = 1.0

#: Registers a callback to run on every file event under the knowledge area (the
#: vault scanner's watch; no second watcher is opened).
WatchKnowledge = Callable[[Callable[[], None]], None]


class KnowledgeSweep:
    """The sweep as a wakeable loop: file events and feature switches wake it."""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        guide: BuiltinGuide,
        features: FeatureService,
        *,
        fallback: float = SWEEP_FALLBACK_S,
        settle: float = SWEEP_SETTLE_S,
    ) -> None:
        self._service = knowledge_service
        self._guide = guide
        self._features = features
        self._loop = WakeableLoop(
            "knowledge-sweep",
            self._pass,
            fallback=fallback,
            settle=settle,
            failure_event="knowledge.sweep.tick_failed",
        )
        self._retry: asyncio.TimerHandle | None = None

    def poke(self) -> None:
        """A file under the knowledge area changed, or the feature was switched."""
        self._loop.poke()

    async def run(self) -> None:
        """Sweep now, then whenever poked or the fallback passes."""
        await self._pass(False)
        await self._loop.serve()

    async def _pass(self, _poked: bool) -> None:
        if not self._features.is_enabled(KNOWLEDGE):
            return
        await sweep_once(self._service, self._guide.refresh)
        await self._schedule_quiet_retry()

    async def _schedule_quiet_retry(self) -> None:
        """A loose document younger than its quiet minute was left alone; look
        again once that minute is over, since no event will announce it."""
        if self._retry is not None:
            self._retry.cancel()
            self._retry = None
        try:
            waiting = await loose_documents_waiting(self._service)
        except Exception:
            _log.warning("knowledge.sweep.quiet_check_failed", exc_info=True)
            return
        if waiting:
            self._retry = asyncio.get_running_loop().call_later(QUIET_SECONDS + 1.0, self.poke)

    def cancel_timers(self) -> None:
        if self._retry is not None:
            self._retry.cancel()
            self._retry = None


def start_knowledge_sweep(
    knowledge_service: KnowledgeService,
    guide: BuiltinGuide,
    resource_svc: ResourceService,
    features: FeatureService,
    watch_knowledge: WatchKnowledge | None = None,
) -> asyncio.Task[None]:
    """Start the sweep; the lifespan cancels the task at shutdown.

    ``resource_svc`` is the registry the service reads its collections from; it is
    taken here so the signature names everything the sweep depends on.
    ``watch_knowledge`` hooks the sweep to the vault's file watch.
    """
    del resource_svc
    sweep = KnowledgeSweep(knowledge_service, guide, features)
    if watch_knowledge is not None:
        watch_knowledge(sweep.poke)
    # Switching knowledge on brings the first sweep forward.
    features.subscribe(lambda key, _enabled: sweep.poke() if key == KNOWLEDGE else None)

    async def serve() -> None:
        try:
            await sweep.run()
        finally:
            sweep.cancel_timers()

    return spawn_restarting(serve, name="knowledge-sweep")


async def stop_knowledge_sweep(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        _log.debug("knowledge.sweep.stopped")
