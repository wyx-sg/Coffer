"""Startup wiring for the tidy pass and its background worker.

Two things only a composition root can supply meet here: the langgraph loop
adapter (import contract 9a keeps langgraph inside ``infrastructure.llm``, so
``application.knowledge`` reaches it only through the injected port) and the
installation-wide switch that decides whether the worker runs at all.

Kept out of ``app.py`` / ``chat_wiring.py``, both at the 400-LOC ceiling,
mirroring the sibling ``*_wiring.py`` modules. Teardown never fires a pending
pass: the tidy is idempotent and the next boot sweeps everything, so making
shutdown wait on an LLM loop would buy nothing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.tidy import TidyPass
from coffer.application.knowledge.tidy_worker import TidyWorker
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.llm.agentic_reorg import LangchainAgenticReorg
from coffer.surfaces.http.knowledge.tidy_state import set_tidy_runner
from coffer.surfaces.http.sync_wiring import SyncWiring

_log = logging.getLogger(__name__)


def wire_tidy(
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
) -> TidyPass:
    """Build the pass and register it for the route, the CLI and the worker."""
    tidy = TidyPass(
        agent=LangchainAgenticReorg(),
        models=models,
        credential_resolver=credential_resolver,
    )
    set_tidy_runner(tidy)
    return tidy


def start_tidy_worker(
    knowledge_service: KnowledgeService,
    tidy: TidyPass,
    resources: ResourceService,
    engine_config: InternalEngineConfigService,
    sync: SyncWiring,
) -> asyncio.Task[None]:
    """Start the interval sweep. It no-ops on every tick until switched on.

    Takes the sync graph explicitly: the worker consults this machine's
    identity, the pending-round state and the vault-write lock, all of which
    ``start_sync`` builds — so sync is wired first (see ``background_workers``).
    Returns the task; the lifespan cancels it at shutdown.
    """

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
        if not (await engine_config.get()).tidy_runs_on(sync.registry.machine_id):
            return False
        # And not while a round is waiting on the user (spec vault-sync
        # "## Unattended rewriters"). A confirmation is answered on the promise
        # that re-deriving the round yields the diff the user was shown, and a
        # rewriter that moves notes underneath them breaks exactly that
        # promise.
        return await sync.state.pending() is None

    worker = TidyWorker(
        service=knowledge_service,
        tidy=tidy,
        is_enabled=is_enabled,
        list_collections=list_collections,
        # The same lock a converge round takes. Both rewrite vault content, and
        # an export caught half-way through a pass is a torn snapshot that git
        # reads as a deliberate change.
        lock=sync.service.lock,
    )
    return asyncio.create_task(worker.run_forever())


async def stop_tidy_worker(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge (a pending pass is
    dropped, never fired — see the module docstring)."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        _log.debug("knowledge.tidy_worker.stopped")
