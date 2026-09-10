"""Wiring for the one ``knowledge`` kind.

Extracted from ``wiring.py`` (which sits at the 400-LOC ceiling) so the kind's
composition — scope resolution, worktree adoption, reconcile-on-append, the
startup reindex sweep — has room. There is ONE service: ``wire_knowledge_kind``
builds it plus the sibling handoff service, registers both tool families
(``coffer__search`` … and the two handoff tools) and the kind's lifecycle hooks;
``run_knowledge_reindex_sweep`` heals the entry index at boot.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.consolidate import StoreConsolidator, find_alias_holder
from coffer.application.knowledge.document_tools import register_document_builtin_tools
from coffer.application.knowledge.handoff import HandoffService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.labels_sync import MemoryLabelsSyncState
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge.scope import GLOBAL_SCOPE_NAME, ScopeResolver
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.stores import build_store_ref_for, project_id_for
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge_scope.project_root_repo import ProjectRootRepo
from coffer.infrastructure.knowledge_scope.scope_fs import (
    git_branch,
    git_root,
    project_identity,
    project_ulid,
)
from coffer.infrastructure.knowledge_scope.store_label_repo import StoreLabelRepo
from coffer.surfaces.http.dependencies import set_knowledge_service
from coffer.surfaces.http.knowledge.dependencies import (
    set_project_root_repo,
    set_scope_label_repo,
)
from coffer.surfaces.http.knowledge.merge_state import set_store_consolidator
from coffer.surfaces.http.wiring import build_substrate

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.knowledge.converter import MarkdownConverter

_log = logging.getLogger(__name__)


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer] | None = None,
    embedding_resolver: EmbeddingResolver = no_embedding,
) -> KnowledgeService:
    """Wire the ``knowledge`` kind into the app and return its one service."""
    documents, retrieval, reindexer = substrate or build_substrate(sm)  # type: ignore[arg-type]
    reconciler = KnowledgeReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer)
    app.state.knowledge_reconciler = reconciler  # reused by the startup reindex sweep
    project_roots = ProjectRootRepo(sm)  # type: ignore[arg-type]
    set_project_root_repo(project_roots)
    label_repo = StoreLabelRepo(sm)  # type: ignore[arg-type]
    set_scope_label_repo(label_repo)
    adopter = StoreConsolidator(
        resources=resource_svc,
        reconciler=reconciler,
        roots=project_roots,
        labels=label_repo,
        scope_dir=paths.scope_dir,
        git_root=git_root,
        project_ulid=project_identity,
    )

    # Shared with the explicit AI-assisted merge (FR-057) so merge + adoption
    # serialize on the same lock; wire_merge picks it up at its own root.
    set_store_consolidator(adopter)

    async def migrate_store(legacy_id: str, new_id: str, root: str) -> None:
        from coffer.application.knowledge.scope import project_scope_name

        await adopter.adopt(project_scope_name(legacy_id), project_scope_name(new_id), root)

    async def merged_alias_target(project_id: str) -> str | None:
        """FR-058: the scope whose ``merged_identities`` lists this identity."""
        return await find_alias_holder(resource_svc, project_id)

    scope = ScopeResolver(
        resources=resource_svc,
        git_root=git_root,
        project_ulid=project_identity,
        scope_dir=paths.scope_dir,
        record_project_root=project_roots.set,
        legacy_project_ulid=project_ulid,
        migrate_store=migrate_store,
        merged_alias_target=merged_alias_target,
    )
    knowledge_service = KnowledgeService(
        resource_service=resource_svc,
        documents=documents,
        scope_resolver=scope,
        reconciler=reconciler,
        retrieval=retrieval,
        reindexer=reindexer,
        # ``ConverterRegistry`` provides the ``convert`` the service calls; it is
        # the production stand-in for the ``MarkdownConverter`` port.
        converters=cast("MarkdownConverter", default_registry()),
        audit=audit,
        paths=paths,
        scope_dir=paths.scope_dir,
        embedding_resolver=embedding_resolver,
    )
    handoff_service = HandoffService(
        scope=scope,
        git_branch=git_branch,
        scope_dir=paths.scope_dir,
        now=lambda: datetime.now(tz=UTC),
    )
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(knowledge_service)
    set_knowledge_service(knowledge_service)
    # Scope labels sync as a state area (spec vault-export-import x FR-017c): a labelled project
    # scope reads by its name on every machine, not "unnamed store".
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(MemoryLabelsSyncState(label_repo))
    register_knowledge_builtin_tools(
        builtin_tools,
        knowledge_service=knowledge_service,
        handoff_service=handoff_service,
    )
    register_document_builtin_tools(
        builtin_tools, resources=resource_svc, knowledge_service=knowledge_service
    )
    return knowledge_service


async def run_knowledge_reindex_sweep(
    app: FastAPI, resources: ResourceService, embedding_resolver: EmbeddingResolver
) -> None:
    """App-facing boot hook: reindex every scope using the reconciler
    ``wire_knowledge_kind`` stashed on ``app.state``."""
    await reindex_all_scopes(
        resources=resources,
        reconciler=app.state.knowledge_reconciler,
        embedding_resolver=embedding_resolver,
    )


async def reindex_all_scopes(
    *,
    resources: ResourceService,
    reconciler: KnowledgeReconciler,
    embedding_resolver: EmbeddingResolver,
) -> None:
    """Index every scope's on-disk knowledge lane so entries written while a
    scope was not being recalled become searchable. Idempotent
    (``content_sha256`` no-op gate) and best-effort — a per-scope failure is
    logged and skipped, never blocking boot."""
    try:
        scopes = await resources.list(kind=KIND_KNOWLEDGE)
    except Exception:
        _log.exception("knowledge_reindex_sweep.list_failed")
        return
    embedding = None
    with contextlib.suppress(Exception):
        embedding = await embedding_resolver()
    for res in scopes:
        ref = build_store_ref_for(res.name, project_id_for(res.name), scope_dir=paths.scope_dir)
        try:
            await reconciler.reconcile(store=ref, embedding=embedding)
        except Exception:
            _log.exception("knowledge_reindex_sweep.scope_failed scope=%s", res.name)


__all__ = [
    "GLOBAL_SCOPE_NAME",
    "reindex_all_scopes",
    "run_knowledge_reindex_sweep",
    "wire_knowledge_kind",
]
