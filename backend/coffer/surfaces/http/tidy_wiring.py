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
        """On, and on the machine that owns the pass.

        Once a vault spans machines an unattended rewriter must run on exactly
        one of them (spec vault-sync ``## Unattended rewriters``): two machines
        merging the same notes produce two *different* topic documents, git
        merges both additions cleanly, and the vault silently holds the
        knowledge twice. No owner set means a single-machine vault, where
        "here" is the only answer there is.
        """
        registry = getattr(app.state, "machine_registry", None)
        machine_id = registry.machine_id if registry is not None else None
        if not (await engine_config.get()).tidy_runs_on(machine_id):
            return False
        # And not while a round is waiting on the user (spec vault-sync
        # "## Unattended rewriters"). A confirmation is answered on the promise
        # that re-deriving the round yields the diff the user was shown, and a
        # rewriter that moves notes underneath them breaks exactly that
        # promise.
        convergence = getattr(app.state, "convergence_state", None)
        return convergence is None or await convergence.pending() is None

    worker = TidyWorker(
        service=knowledge_service,
        tidy=app.state.tidy_pass,
        is_enabled=is_enabled,
        list_collections=list_collections,
        # The same lock a converge round takes. Both rewrite vault content, and
        # an export caught half-way through a pass is a torn snapshot that git
        # reads as a deliberate change.
        lock=getattr(getattr(app.state, "sync_service", None), "lock", None),
    )
    app.state.tidy_worker_task = asyncio.create_task(worker.run_forever())


async def stop_tidy_worker(app: FastAPI) -> None:
    task = getattr(app.state, "tidy_worker_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
