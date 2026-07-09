"""Wiring for the ``memory`` kind (spec 007).

Extracted from ``wiring.py`` (which sits at the 400-LOC ceiling) so the memory
kind's growing composition — reconcile-on-append, the startup reindex sweep —
has room. ``wire_memory_kind`` builds the memory service + its sibling handoff
and journal services; ``run_memory_reindex_sweep`` heals the search index at
boot.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.memory.builtin_tools import register_memory_builtin_tools
from coffer.application.memory.handoff import HandoffService
from coffer.application.memory.journal import JournalService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.scope import GLOBAL_STORE_NAME, ScopeResolver
from coffer.application.memory.service import MemoryService
from coffer.application.memory.stores import build_store_ref_for
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.knowledge.document import KIND_MEMORY, WORKSPACE_GLOBAL_PROJECT_ID
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import git_branch, git_root, project_ulid
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo
from coffer.surfaces.http.dependencies import set_memory_service
from coffer.surfaces.http.memory.dependencies import (
    set_journal_service,
    set_project_root_repo,
    set_store_label_repo,
)
from coffer.surfaces.http.wiring import build_substrate

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService

_log = logging.getLogger(__name__)


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer] | None = None,
    embedding_resolver: EmbeddingResolver = no_embedding,
) -> MemoryService:
    """Wire the ``memory`` kind (spec 007) into the app."""
    documents, retrieval, reindexer = substrate or build_substrate(sm)  # type: ignore[arg-type]
    reconciler = MemoryReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer)
    app.state.memory_reconciler = reconciler  # reused by the startup reindex sweep
    project_roots = ProjectRootRepo(sm)  # type: ignore[arg-type]
    set_project_root_repo(project_roots)
    set_store_label_repo(StoreLabelRepo(sm))  # type: ignore[arg-type]
    scope = ScopeResolver(
        resources=resource_svc,
        git_root=git_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
        record_project_root=project_roots.set,
    )
    memory_service = MemoryService(
        resource_service=resource_svc,
        documents=documents,
        scope_resolver=scope,
        reconciler=reconciler,
        retrieval=retrieval,
        audit=audit,
        store_dir=paths.memory_store_dir,
        embedding_resolver=embedding_resolver,
    )
    handoff_service = HandoffService(
        scope=scope,
        git_branch=git_branch,
        store_dir=paths.memory_store_dir,
        audit=audit,
        now=lambda: datetime.now(tz=UTC),
    )
    journal_service = JournalService(
        scope=scope,
        store_dir=paths.memory_store_dir,
        audit=audit,
        now=lambda: datetime.now(tz=UTC),
        # Reconcile-on-append: a distilled journal entry is indexed immediately
        # so it is recall-able without waiting for a lazy reconcile-on-read.
        reconciler=reconciler,
        embedding=embedding_resolver,
    )
    set_journal_service(journal_service)
    app.state.kinds["memory"] = make_memory_kind(memory_service)
    set_memory_service(memory_service)
    register_memory_builtin_tools(
        builtin_tools, memory_service=memory_service, handoff_service=handoff_service
    )
    return memory_service


async def run_memory_reindex_sweep(
    app: FastAPI, resources: ResourceService, embedding_resolver: EmbeddingResolver
) -> None:
    """App-facing boot hook: reindex every memory store using the reconciler
    ``wire_memory_kind`` stashed on ``app.state``."""
    await reindex_all_memory_stores(
        resources=resources,
        reconciler=app.state.memory_reconciler,
        embedding_resolver=embedding_resolver,
    )


async def reindex_all_memory_stores(
    *,
    resources: ResourceService,
    reconciler: MemoryReconciler,
    embedding_resolver: EmbeddingResolver,
) -> None:
    """Index every memory store's on-disk lanes so journal written while a store
    was not being recalled becomes searchable (FR-043). Idempotent
    (``content_sha256`` no-op gate) and best-effort — a per-store failure is
    logged and skipped, never blocking boot."""
    try:
        stores = await resources.list(kind=KIND_MEMORY)
    except Exception:
        _log.exception("memory_reindex_sweep.list_failed")
        return
    embedding = None
    with contextlib.suppress(Exception):
        embedding = await embedding_resolver()
    for res in stores:
        project_id = (
            WORKSPACE_GLOBAL_PROJECT_ID
            if res.name == GLOBAL_STORE_NAME
            else res.name.removeprefix("project-")
        )
        ref = build_store_ref_for(res.name, project_id, store_dir=paths.memory_store_dir)
        try:
            await reconciler.reconcile(store=ref, embedding=embedding)
        except Exception:
            _log.exception("memory_reindex_sweep.store_failed store=%s", res.name)
