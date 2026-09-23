"""Startup wiring for the curation pass and its background worker.

Three things only a composition root can supply meet here: the langgraph loop
adapter (import contract 9a keeps langgraph inside ``infrastructure.llm``, so
``application.knowledge`` reaches it only through the injected port), the
installation-wide switch that decides whether the worker runs, and Coffer's
own skill, which the pass re-renders after every corpus change — a new
document is unreachable until the catalogue in that skill names it.

Kept out of ``app.py`` / ``chat_wiring.py``, both at the 400-LOC ceiling,
mirroring the sibling ``*_wiring.py`` modules. Teardown never fires a pending
pass: the watermark makes a sweep idempotent and the next boot picks up
whatever was left, so making shutdown wait on an LLM loop would buy nothing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.knowledge.curate import CurationPass
from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.domain.internal_engine_config import CURATE
from coffer.infrastructure.llm.agentic_reorg import LangchainAgenticReorg
from coffer.surfaces.http.engine_config_composition import read_internal_engine_timeout
from coffer.surfaces.http.guide_wiring import BuiltinGuide
from coffer.surfaces.http.knowledge.curation_state import set_curation_runner
from coffer.surfaces.http.sync_wiring import SyncWiring

_log = logging.getLogger(__name__)


def wire_curation(
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
    guide: BuiltinGuide,
) -> CurationPass:
    """Build the pass and register it for the route, the CLI and the worker."""

    async def _redeliver() -> None:
        # One rendering for the machine: the catalogue is the whole enabled
        # corpus, not a per-agent slice of it, so every agent's copy is the
        # same bytes and re-seeding the master updates all of them at once.
        await guide.refresh()

    curation = CurationPass(
        agent=LangchainAgenticReorg(),
        models=models,
        credential_resolver=credential_resolver,
        on_corpus_changed=_redeliver,
        read_timeout=read_internal_engine_timeout,
    )
    set_curation_runner(curation)
    return curation


async def curation_may_run(engine_config: InternalEngineConfigService, sync: SyncWiring) -> bool:
    """On, and on the machine that owns the pass.

    Once a vault spans machines an unattended rewriter must run on exactly
    one of them (spec vault-sync "Run an unattended rewriter on one owner
    machine"): two machines folding the same material produce two *different*
    documents, git merges both additions cleanly, and the vault silently holds
    the knowledge twice. No owner set means a single-machine vault, where
    "here" is the only answer there is.
    """
    if not (await engine_config.get()).curate_runs_on(sync.registry.machine_id):
        return False
    # And not while a round is waiting on the user — a held confirmation or
    # an unresolved conflict (spec vault-sync "Never overlap a tidy pass and a
    # round"). A confirmation is answered on the promise that re-deriving the
    # round yields the diff the user was shown, and a conflict is a choice
    # between two versions; a rewriter that moves documents underneath either
    # breaks exactly that.
    return not await sync.service.divergence_outstanding()


def start_curation_worker(
    knowledge_service: KnowledgeService,
    curation: CurationPass,
    guide: BuiltinGuide,
    resources: ResourceService,
    engine_config: InternalEngineConfigService,
    sync: SyncWiring,
) -> asyncio.Task[None]:
    """Start the interval sweep.

    It is **on by default** (spec knowledge "Curate on one owner machine
    only"): curation is what merges new material into
    the documents an agent reads, so an installation where it never runs is one
    whose inbox is never read. Returns the task; the lifespan cancels it at
    shutdown.

    Takes the sync graph explicitly: the worker consults this machine's
    identity, the outstanding-round state and the vault-write lock, all of which
    ``start_sync`` builds — so sync is wired first (see ``background_workers``).
    """

    async def list_collections() -> list[str]:
        # The registry is the authority on which collections exist; the
        # application layer must not go looking for directories to answer it.
        #
        # Uids, not names. A sweep holds one of these across a pass that takes
        # minutes and rewrites a corpus, and the worker claims it in the same
        # upkeep-runs table the page's Curate button claims — so it has to be
        # the value that cannot be edited underneath either of them (ADR
        # resource-identity-is-an-immutable-uid). The worker reads the
        # directory name off the row itself.
        return [r.uid for r in await resources.list(kind=KIND_KNOWLEDGE, enabled=True)]

    async def is_enabled() -> bool:
        return await curation_may_run(engine_config, sync)

    async def read_interval() -> int | None:
        """The operator's interval for this pass, re-read while the wait runs
        (spec internal-engine "Apply a changed switch or interval without a
        restart") — a value captured at boot would be stale
        the moment another machine's setting converged in."""
        return (await engine_config.get()).upkeep(CURATE).interval_s

    worker = CurationWorker(
        service=knowledge_service,
        curate=curation,
        deliver=guide.refresh,
        is_enabled=is_enabled,
        read_interval=read_interval,
        list_collections=list_collections,
        # The same lock a converge round takes. Both rewrite vault content, and
        # an export caught half-way through a pass is a torn snapshot that git
        # reads as a deliberate change.
        lock=sync.service.lock,
    )
    return asyncio.create_task(worker.run_forever())


async def stop_curation_worker(task: asyncio.Task[None]) -> None:
    """Cancel the sweep and wait for it to acknowledge (a pending pass is
    dropped, never fired — see the module docstring)."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        _log.debug("knowledge.curate_worker.stopped")
