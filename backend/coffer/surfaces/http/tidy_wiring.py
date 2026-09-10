"""Startup wiring for the notes tidy trigger.

Kept out of ``app.py`` / ``wiring.py`` (both at the 400-LOC ceiling), mirroring
the sibling ``*_wiring.py`` modules. ``reorg_wiring.py`` builds the pass; this
module decides when it runs, and owns the two things only a composition root
can supply:

- the write-notify hook, so a burst of ``coffer__write`` calls settles into one
  tidy once the session goes quiet;
- the list of scopes for the periodic sweep, read from the resource registry.
  The registry is the authority on which scopes exist — the application layer
  must not go looking for directories on disk to answer that.

The sweep task is started and stopped exactly like ``RetentionWorker``: a task
handle on ``app.state``, cancelled on the way down. Teardown never fires a
pending tidy: the pass is idempotent and the next boot sweeps everything anyway,
so making a shutdown wait on an LLM loop would buy nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from coffer.application.knowledge.tidy_trigger import NotesTidyTrigger
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.knowledge.reorg_state import get_reorg_service

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.knowledge.service import KnowledgeService


def start_tidy(app: FastAPI, knowledge_service: KnowledgeService) -> NotesTidyTrigger:
    """Arm the tidy pass and start its periodic sweep.

    Must be called AFTER ``wire_reorg`` (the pass has to exist) and
    ``wire_knowledge_kind`` (the write-notify hook lives on the service).
    """
    resources = get_resource_service()

    async def list_scopes() -> list[str]:
        return [r.name for r in await resources.list(kind=KIND_KNOWLEDGE)]

    trigger = NotesTidyTrigger(tidy=get_reorg_service(), list_scopes=list_scopes)
    knowledge_service.set_on_change(trigger.on_change)
    app.state.notes_tidy_trigger = trigger
    app.state.notes_tidy_task = asyncio.create_task(trigger.run())
    return trigger


async def stop_tidy(app: FastAPI) -> None:
    """Best-effort teardown: never raises, never blocks on a running pass."""
    trigger: Any = getattr(app.state, "notes_tidy_trigger", None)
    if trigger is not None:
        with contextlib.suppress(Exception):
            await trigger.shutdown()
    task: asyncio.Task[None] | None = getattr(app.state, "notes_tidy_task", None)
    if task is None:
        return
    # ``shutdown()`` already signalled the loop; cancel rather than wait, so a
    # sweep parked on an in-flight model call cannot hold the daemon open.
    task.cancel()
    with contextlib.suppress(BaseException):
        await task


__all__ = ["start_tidy", "stop_tidy"]
