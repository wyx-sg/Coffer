"""Startup wiring for the one-time boot heals of the knowledge file tree.

Two of them, both idempotent and both best-effort, run in this order at daemon
boot: the collapse to the two-lane on-disk layout, then the consolidation of
per-project scopes that git worktrees had fragmented. The layout migration goes
FIRST because everything downstream — the consolidation, the reindex sweep, the
lane reads — addresses a scope through the new directory names and would see an
un-migrated vault as empty.

Kept out of ``app.py`` / ``wiring.py`` (both at the 400-LOC ceiling), mirroring
the sibling ``*_wiring.py`` modules.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from coffer.application.knowledge.consolidate import ConsolidationReport, StoreConsolidator
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge_scope.lane_migration import migrate_knowledge_root
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


async def run_lane_migration() -> None:
    """Bring every scope on disk to the two-lane layout (2026-09-11).

    A blocking filesystem sweep, so it runs off the event loop. Idempotent: a
    vault already migrated has no ``knowledge/`` or ``inbox/`` left to act on,
    so every boot after the first does nothing and costs one directory listing.

    Never raises. A vault that cannot be migrated is still readable — the lazy
    reindex-on-read derives every path from the files actually on disk — so a
    failure here must not stop the daemon from starting.
    """
    try:
        report = await asyncio.to_thread(migrate_knowledge_root, paths.knowledge_root())
    except Exception:
        _log.warning("knowledge.lane_migration.failed", exc_info=True)
        return
    if report.did_work:
        _log.info(
            "knowledge.lane_migration.done",
            extra={
                "scopes": report.scopes_migrated,
                "notes_moved": report.notes_moved,
                "docs_lane_renamed": report.docs_lane_renamed,
                "retired_removed": report.retired_removed,
                "failures": report.failures,
            },
        )
