"""Wiring for the transcript summary cache's warm pass (FR-047).

Mirrors ``memory_wiring.py``'s ``start_organise_worker`` /
``stop_organise_worker`` pair: the worker itself is pure application code, and
this is the one place that knows how to turn registered agents into the
``(type, config_dir)`` pairs it warms.

The reader is handed in rather than looked up, and it is the same instance the
listing uses (``agent_skill_wiring`` returns it): a second one would warm a
second cache and leave the listing's own as cold as it found it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from coffer.application.agent.transcript_warm_worker import AgentTarget, TranscriptWarmWorker
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.transcripts import supports_transcripts

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService
    from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader

logger = logging.getLogger(__name__)


def start_transcript_warm_worker(
    reader: FileTranscriptReader, resource_svc: ResourceService
) -> tuple[TranscriptWarmWorker, asyncio.Task[None]]:
    """Start the warm pass over every registered agent that has transcripts.

    Returns the worker with its task: stopping it is two steps, because the
    pass is blocking disk work on a thread and asking it to stop between files
    is kinder than cancelling mid-parse.
    """

    async def _list_targets() -> list[AgentTarget]:
        # Registered agents, enabled or not: the Conversations tab reads an
        # agent's own past sessions, which a disabled agent still has. Listing
        # resources is a read — it emits no audit event, which is what FR-011
        # requires of anything behind a workspace listing.
        targets: list[AgentTarget] = []
        for resource in await resource_svc.list(kind="agent"):
            cfg = AgentConfig.model_validate(resource.config)
            if supports_transcripts(cfg.type.value):
                targets.append((cfg.type.value, str(cfg.resolved_config_dir())))
        return targets

    def _warm(agent_type_value: str, config_dir: str) -> int:
        return int(reader.warm(agent_type_value=agent_type_value, config_dir=config_dir))

    worker = TranscriptWarmWorker(warm=_warm, list_targets=_list_targets)
    return worker, asyncio.create_task(worker.run())


async def stop_transcript_warm_worker(
    worker: TranscriptWarmWorker, task: asyncio.Task[None]
) -> None:
    """Signal the warm pass to stop and wait for the tick to unwind."""
    worker.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.debug("agent.transcript_warm_worker.stopped")
