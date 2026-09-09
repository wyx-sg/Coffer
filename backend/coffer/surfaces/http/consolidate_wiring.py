"""Startup wiring for the one-time worktree-scope consolidation.

Kept out of ``app.py`` / ``wiring.py`` (both at the 400-LOC ceiling), mirroring
the sibling ``*_wiring.py`` modules. Builds a :class:`StoreConsolidator` from the
shared substrate + session maker and runs it best-effort at daemon boot.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.knowledge.consolidate import ConsolidationReport, StoreConsolidator
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge_scope.project_root_repo import ProjectRootRepo
from coffer.infrastructure.knowledge_scope.scope_fs import git_root, project_identity
from coffer.infrastructure.knowledge_scope.store_label_repo import StoreLabelRepo

if TYPE_CHECKING:
    from coffer.application.knowledge.reindex import Reindexer
    from coffer.application.knowledge.retrieval import KnowledgeRetrieval
    from coffer.application.resource_service import ResourceService
    from coffer.infrastructure.knowledge.repository import DocumentRepo

_log = logging.getLogger(__name__)


async def run_store_consolidation(
    *,
    resources: ResourceService,
    sm: object,
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer],
) -> ConsolidationReport:
    """Heal per-project knowledge scopes fragmented across git worktrees by the old
    path-hash bug. Best-effort and idempotent: never raises, and a second boot
    after a clean pass is a no-op."""
    documents, retrieval, reindexer = substrate
    consolidator = StoreConsolidator(
        resources=resources,
        reconciler=KnowledgeReconciler(
            documents=documents, retrieval=retrieval, reindexer=reindexer
        ),
        roots=ProjectRootRepo(sm),  # type: ignore[arg-type]
        labels=StoreLabelRepo(sm),  # type: ignore[arg-type]
        scope_dir=paths.scope_dir,
        git_root=git_root,
        project_ulid=project_identity,
    )
    try:
        return await consolidator.run()
    except Exception:
        _log.exception("store_consolidation.failed")
        return ConsolidationReport()
