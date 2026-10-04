"""Startup wiring for the knowledge sweep, the one background timer knowledge has.

Every tick runs :func:`coffer.application.knowledge.sweep.sweep_once`: it promotes
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

from coffer.application.features import FeatureService
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.sweep import sweep_once
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.features import KNOWLEDGE
from coffer.surfaces.http.guide_wiring import BuiltinGuide

_log = logging.getLogger(__name__)

#: Seconds between ticks. Fixed: nothing the sweep does is worth tuning, and the
#: wait is short enough that a file dropped into an inbox is a document within a
#: minute.
SWEEP_INTERVAL_S = 60.0


async def _run_forever(
    knowledge_service: KnowledgeService, guide: BuiltinGuide, features: FeatureService
) -> None:
    while True:
        if features.is_enabled(KNOWLEDGE):
            try:
                await sweep_once(knowledge_service, guide.refresh)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed tick must never end the loop: the next one is a fresh
                # attempt over whatever is still waiting.
                _log.warning("knowledge.sweep.tick_failed", exc_info=True)
        await asyncio.sleep(SWEEP_INTERVAL_S)


def start_knowledge_sweep(
    knowledge_service: KnowledgeService,
    guide: BuiltinGuide,
    resource_svc: ResourceService,
    features: FeatureService,
) -> asyncio.Task[None]:
    """Start the interval sweep; the lifespan cancels the task at shutdown.

    ``resource_svc`` is the registry the service reads its collections from; it is
    taken here so the signature names everything the sweep depends on.
    """
    del resource_svc
    return spawn_restarting(
        lambda: _run_forever(knowledge_service, guide, features), name="knowledge-sweep"
    )


async def stop_knowledge_sweep(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        _log.debug("knowledge.sweep.stopped")
