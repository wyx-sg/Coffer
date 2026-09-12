"""Startup wiring for the tidy pass and its background worker.

Two things only a composition root can supply meet here: the langgraph loop
adapter (import contract 9a keeps langgraph inside ``infrastructure.llm``, so
``application.knowledge`` reaches it only through the injected port) and the
installation-wide switch that decides whether the worker runs at all.

Kept out of ``app.py`` / ``wiring.py``, both at the 400-LOC ceiling, mirroring
the sibling ``*_wiring.py`` modules. Teardown never fires a pending pass: the
tidy is idempotent and the next boot sweeps everything, so making shutdown wait
on an LLM loop would buy nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.tidy import TidyPass
from coffer.application.knowledge.tidy_worker import TidyWorker
from coffer.infrastructure.llm.agentic_reorg import LangchainAgenticReorg
from coffer.surfaces.http.dependencies import (
    get_internal_engine_config_service,
    get_resource_service,
)
from coffer.surfaces.http.knowledge.tidy_state import set_tidy_runner

if TYPE_CHECKING:
    from fastapi import FastAPI


def wire_tidy(
    app: FastAPI,
    knowledge_service: KnowledgeService,
    models: Any,
    credential_resolver: Any,
) -> TidyPass:
    """Build the pass and register it for the route, the CLI and the worker."""
    tidy = TidyPass(
        agent=LangchainAgenticReorg(),
        models=models,
        credential_resolver=credential_resolver,
    )
    set_tidy_runner(tidy)
    app.state.tidy_pass = tidy
    return tidy


def start_tidy_worker(app: FastAPI, knowledge_service: KnowledgeService) -> None:
    """Start the interval sweep. It no-ops on every tick until switched on."""
    resources = get_resource_service()
    engine_config = get_internal_engine_config_service()

    async def list_collections() -> list[str]:
        # The registry is the authority on which collections exist; the
        # application layer must not go looking for directories to answer it.
        return [r.name for r in await resources.list(kind=KIND_KNOWLEDGE, enabled=True)]

    async def is_enabled() -> bool:
        return (await engine_config.get()).auto_tidy_enabled

    worker = TidyWorker(
        service=knowledge_service,
        tidy=app.state.tidy_pass,
        is_enabled=is_enabled,
        list_collections=list_collections,
    )
    app.state.tidy_worker_task = asyncio.create_task(worker.run_forever())


async def stop_tidy_worker(app: FastAPI) -> None:
    task = getattr(app.state, "tidy_worker_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
