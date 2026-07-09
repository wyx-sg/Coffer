"""Startup wiring for the one-time worktree-store consolidation (spec 007).

Kept out of ``app.py`` / ``wiring.py`` (both at the 400-LOC ceiling), mirroring
the sibling ``*_wiring.py`` modules. Builds a :class:`StoreConsolidator` from the
shared substrate + session maker and runs it best-effort at daemon boot.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.memory.consolidate import ConsolidationReport, StoreConsolidator
from coffer.application.memory.sync import MemoryReconciler
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import git_root, project_ulid
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo

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
    """Heal per-project memory stores fragmented across git worktrees by the old
    path-hash bug. Best-effort and idempotent: never raises, and a second boot
    after a clean pass is a no-op."""
    documents, retrieval, reindexer = substrate
    consolidator = StoreConsolidator(
        resources=resources,
        reconciler=MemoryReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer),
        roots=ProjectRootRepo(sm),  # type: ignore[arg-type]
        labels=StoreLabelRepo(sm),  # type: ignore[arg-type]
        store_dir=paths.memory_store_dir,
        git_root=git_root,
        project_ulid=project_ulid,
    )
    try:
        return await consolidator.run()
    except Exception:
        _log.exception("store_consolidation.failed")
        return ConsolidationReport()
