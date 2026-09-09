"""Scope-level admin operations for ``KnowledgeService`` — provision / rebuild /
teardown.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. Free functions over injected collaborators, like ``writes``/
``queries``; the service passes its own bound methods as the callables.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from collections.abc import Awaitable, Callable

from coffer.application.knowledge.ports import KnowledgeDocumentRepo
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge.scope import GLOBAL_SCOPE_NAME, is_project_scope_name
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.domain.errors import (
    MemoryStoreNotFound,
    ResourceAlreadyExists,
    ResourceNotFound,
)
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge.scope import ResolvedScope
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)

#: ``scope_name -> config`` (validates the store exists).
ConfigFn = Callable[[str], Awaitable[KnowledgeConfig]]
#: ``scope_name -> ResolvedScope``.
ResolvedForFn = Callable[[str], Awaitable[ResolvedScope]]
#: ``scope_name, project_id -> StoreRef``.
StoreRefFn = Callable[[str, str], StoreRef]


async def ensure_scope(
    *,
    resources: object,
    provision_global: Callable[[], Awaitable[object]],
    scope_name: str,
) -> None:
    """Provision an auto-scope's Resource if absent (surfaces address scopes by
    name). ``global`` auto-provisions on first REST access; a ``project-<ulid>``
    scope is provisioned directly (no cwd needed).

    A **named collection is never provisioned here** — it exists because someone
    created it deliberately, so an unknown name is a 404 rather than a new empty
    collection conjured from a typo. Creating one goes through the ordinary
    Resource-registration surface."""
    if scope_name != GLOBAL_SCOPE_NAME and not is_project_scope_name(scope_name):
        raise MemoryStoreNotFound(scope_name)
    ref = ResourceRef(kind=KIND_KNOWLEDGE, name=scope_name)
    try:
        await resources.get(ref)  # type: ignore[attr-defined]
        return
    except ResourceNotFound:
        pass
    if scope_name == GLOBAL_SCOPE_NAME:
        await provision_global()
        return
    # suppress: concurrent first access — another request provisioned it first.
    with contextlib.suppress(ResourceAlreadyExists):
        await resources.register(  # type: ignore[attr-defined]
            kind=KIND_KNOWLEDGE,
            name=scope_name,
            config=KnowledgeConfig().model_dump(mode="json"),
            actor="system",
        )


async def reindex_scope(
    *,
    get_config: ConfigFn,
    resolved_for: ResolvedForFn,
    store_ref: StoreRefFn,
    reconciler: KnowledgeReconciler,
    scope_name: str,
    config: KnowledgeConfig | None = None,
    embedding_resolver: EmbeddingResolver = no_embedding,
) -> None:
    """Force-rebuild a scope's entry index under ``config`` (defaults to the
    stored config). Called by the kind's ``on_update_config`` hook so toggling
    vector re-embeds entries written before the change — the sha no-op gate
    would otherwise leave the new vec table empty forever. Embedding is
    global. The ingestion lane is rebuilt separately by the caller."""
    cfg = config if config is not None else await get_config(scope_name)
    resolved = await resolved_for(scope_name)
    ref = store_ref(scope_name, resolved.project_id)
    embedding = await embedding_resolver() if cfg.vector_enabled else None
    await reconciler.reconcile(store=ref, embedding=embedding, force=True)


async def cleanup_scope(
    *,
    get_config: ConfigFn,
    resolved_for: ResolvedForFn,
    store_ref: StoreRefFn,
    documents: KnowledgeDocumentRepo,
    retrieval: KnowledgeRetrieval,
    reconciler: KnowledgeReconciler,
    scope_name: str,
) -> None:
    """Drop a scope's rows, vec table and on-disk dir (the on_delete hook).

    Runs under the reconciler's per-scope lock so a concurrent recall's
    reconcile cannot scan the dir mid-teardown and re-insert rows for the
    deleted scope. The rmtree takes the whole scope dir, so the ingestion
    lane's files go with the entry lanes."""
    config = await get_config(scope_name)
    resolved = await resolved_for(scope_name)
    async with reconciler.lock_for(scope_name):
        await documents.delete_resource(KIND_KNOWLEDGE, scope_name)
        # Drop the per-store sqlite-vec table too (lives outside the async
        # session → leaks across a same-name re-create otherwise — finding #6).
        # Maintenance mode (dimensions=None) drops whatever width exists; the
        # global embedding dimension is irrelevant to teardown.
        _ = config  # retained for signature symmetry; embedding is global now
        try:
            await retrieval.drop_store(store_ref(scope_name, resolved.project_id), dimensions=None)
        except Exception:
            _logger.warning(
                "knowledge.cleanup.drop_vec_store_failed",
                extra={"scope": scope_name},
                exc_info=True,
            )
        if resolved.store_dir.exists():
            await asyncio.to_thread(shutil.rmtree, resolved.store_dir, ignore_errors=True)
