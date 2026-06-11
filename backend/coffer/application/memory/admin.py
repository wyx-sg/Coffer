"""Store-level admin operations for ``MemoryService`` — provision / rebuild /
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

from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.scope import GLOBAL_STORE_NAME, is_valid_store_name
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.errors import (
    MemoryStoreNotFound,
    ResourceAlreadyExists,
    ResourceNotFound,
)
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import ResolvedScope
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)

#: ``store_name -> config`` (validates the store exists).
ConfigFn = Callable[[str], Awaitable[MemoryStoreConfig]]
#: ``store_name -> ResolvedScope``.
ResolvedForFn = Callable[[str], Awaitable[ResolvedScope]]
#: ``store_name, project_id -> StoreRef``.
StoreRefFn = Callable[[str, str], StoreRef]


async def ensure_store(
    *,
    resources: object,
    provision_global: Callable[[], Awaitable[object]],
    store_name: str,
) -> None:
    """Provision a store's Resource if absent (surfaces address stores by
    name). The global store auto-provisions on first REST access; a
    ``project-<ulid>`` store is provisioned directly (no cwd needed). An
    arbitrary name is rejected (404) — it must never manufacture a Resource."""
    if not is_valid_store_name(store_name):
        raise MemoryStoreNotFound(store_name)
    ref = ResourceRef(kind=KIND_MEMORY, name=store_name)
    try:
        await resources.get(ref)  # type: ignore[attr-defined]
        return
    except ResourceNotFound:
        pass
    if store_name == GLOBAL_STORE_NAME:
        await provision_global()
        return
    # suppress: concurrent first access — another request provisioned it first.
    with contextlib.suppress(ResourceAlreadyExists):
        await resources.register(  # type: ignore[attr-defined]
            kind=KIND_MEMORY,
            name=store_name,
            config=MemoryStoreConfig().model_dump(mode="json"),
            actor="system",
        )


async def reindex_store(
    *,
    get_config: ConfigFn,
    resolved_for: ResolvedForFn,
    store_ref: StoreRefFn,
    reconciler: MemoryReconciler,
    store_name: str,
    config: MemoryStoreConfig | None = None,
) -> None:
    """Force-rebuild a store's index under ``config`` (defaults to the stored
    config). Called by the kind's ``on_update_config`` hook so that enabling
    vector (or changing the embedding model) re-embeds facts written before
    the change — the sha no-op gate would otherwise leave the new vec table
    empty forever."""
    cfg = config if config is not None else await get_config(store_name)
    resolved = await resolved_for(store_name)
    ref = store_ref(store_name, resolved.project_id)
    embedding = cfg.to_embedding_config() if cfg.vector_enabled else None
    await reconciler.reconcile(store=ref, embedding=embedding, force=True)


async def cleanup_store(
    *,
    get_config: ConfigFn,
    resolved_for: ResolvedForFn,
    store_ref: StoreRefFn,
    documents: MemoryDocumentRepo,
    retrieval: KnowledgeRetrieval,
    store_name: str,
) -> None:
    """Drop a store's rows, vec table and on-disk dir (the on_delete hook)."""
    config = await get_config(store_name)
    resolved = await resolved_for(store_name)
    await documents.delete_resource(KIND_MEMORY, store_name)
    # Drop the per-store sqlite-vec table too (lives outside the async
    # session → leaks across a same-name re-create otherwise — finding #6).
    dims = config.embedding_dimensions if config.vector_enabled else None
    try:
        await retrieval.drop_store(store_ref(store_name, resolved.project_id), dimensions=dims)
    except Exception:
        _logger.warning(
            "memory.cleanup.drop_vec_store_failed",
            extra={"store": store_name},
            exc_info=True,
        )
    if resolved.store_dir.exists():
        await asyncio.to_thread(shutil.rmtree, resolved.store_dir, ignore_errors=True)
