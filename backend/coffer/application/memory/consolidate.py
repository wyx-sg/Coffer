"""One-time consolidation of duplicate per-project memory stores.

Before the ``git_root`` worktree fix, the same repo checked out in several git
worktrees hashed to a distinct ``project_ulid`` each, so its memory fragmented
across ``project-<ulid>`` stores. This heals that: re-resolve every recorded
store root through the (now worktree-aware) ``git_root``; any store whose name
is no longer the canonical ``project-<ulid>`` for its root is merged into the
canonical store and retired.

Runs once, best-effort, at daemon startup (see ``surfaces/http/app.py``). It is
idempotent: after a merge the stale store's files, resource, documents rows,
label and root mapping are gone, so a second pass sees only canonical stores and
does nothing. Merging is additive-only — the canonical store's own files are
never deleted, so real memory can never be lost, only gained.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from coffer.application.memory.scope import (
    GLOBAL_STORE_NAME,
    KIND_MEMORY,
    project_store_name,
)
from coffer.application.memory.stores import build_store_ref_for
from coffer.application.memory.sync import MemoryReconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.fs import atomic_write_text
from coffer.infrastructure.memory.journal_files import append_entry, read_entries
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo

_logger = logging.getLogger("coffer.memory.consolidate")

GitRootFn = Callable[[str], "Path | None"]
ProjectUlidFn = Callable[[str], str]
StoreDirFn = Callable[[str], Path]

#: Machine-local / derived files that are never merged (regenerated per store).
_DERIVED_NAMES = frozenset({"MEMORY.md", "INDEX.md", "consolidation-log.md"})


@dataclass
class ConsolidationReport:
    """What a consolidation pass did — surfaced in the startup log."""

    merged_stores: list[str] = field(default_factory=list)
    retired_empty: list[str] = field(default_factory=list)
    unresolvable: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.merged_stores or self.retired_empty)


def merge_store_dir(src: Path, dst: Path, *, tag: str) -> int:
    """Merge every lane file under ``src`` into ``dst`` (additive). Returns the
    number of files merged/created.

    - ``journal/<period>.md`` files are content-merged entry-by-entry, deduped by
      timestamp, so overlapping days never duplicate or overwrite.
    - Derived/machine-local files are skipped.
    - Any other name collision keeps BOTH copies (the incoming one is suffixed
      ``--from-<tag>``) so nothing is ever clobbered.
    """
    if not src.exists():
        return 0
    merged = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        if rel.name in _DERIVED_NAMES:
            continue
        target = dst / rel
        if rel.parts[0] == "journal" and rel.suffix == ".md":
            if _merge_journal_file(path, target):
                merged += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = _suffixed(target, tag)
        atomic_write_text(target, path.read_text(encoding="utf-8"))
        merged += 1
    return merged


def _merge_journal_file(src_file: Path, dst_file: Path) -> bool:
    """Append entries from ``src_file`` into ``dst_file`` that aren't already
    there (deduped by ISO timestamp). Returns whether anything was written."""
    existing = {e.timestamp.isoformat() for e in read_entries(dst_file)}
    wrote = False
    for entry in read_entries(src_file):
        if entry.timestamp.isoformat() in existing:
            continue
        append_entry(dst_file, timestamp=entry.timestamp, body=entry.body)
        existing.add(entry.timestamp.isoformat())
        wrote = True
    return wrote


def _suffixed(target: Path, tag: str) -> Path:
    """A non-colliding sibling of ``target`` marked with the source ``tag``."""
    candidate = target.with_name(f"{target.stem}--from-{tag}{target.suffix}")
    n = 2
    while candidate.exists():
        candidate = target.with_name(f"{target.stem}--from-{tag}-{n}{target.suffix}")
        n += 1
    return candidate


class StoreConsolidator:
    """Collapses duplicate project memory stores into their canonical store."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        reconciler: MemoryReconciler,
        roots: ProjectRootRepo,
        labels: StoreLabelRepo,
        store_dir: StoreDirFn,
        git_root: GitRootFn,
        project_ulid: ProjectUlidFn,
    ) -> None:
        self._resources = resources
        self._reconciler = reconciler
        self._roots = roots
        self._labels = labels
        self._store_dir = store_dir
        self._git_root = git_root
        self._project_ulid = project_ulid

    async def run(self) -> ConsolidationReport:
        report = ConsolidationReport()
        for store_name, project_root in await self._roots.list_all():
            if store_name == GLOBAL_STORE_NAME:
                continue
            root = self._git_root(project_root)
            if root is None:
                report.unresolvable.append(store_name)
                continue
            canonical = project_store_name(self._project_ulid(str(root)))
            if canonical == store_name:
                if str(root) != project_root:  # normalise a drifted root string
                    await self._roots.set(store_name, str(root))
                continue
            try:
                await self._merge_and_retire(store_name, canonical, str(root), report)
            except Exception:  # best-effort: a failure leaves the stale store intact
                _logger.exception("consolidate.store.failed store=%s", store_name)
                report.failed.append(store_name)
        if report.changed or report.failed:
            _logger.info(
                "consolidate.done merged=%s retired_empty=%s unresolvable=%s failed=%s",
                report.merged_stores,
                report.retired_empty,
                report.unresolvable,
                report.failed,
            )
        return report

    async def _merge_and_retire(
        self, stale: str, canonical: str, root: str, report: ConsolidationReport
    ) -> None:
        stale_dir = self._store_dir(_ulid_of(stale))
        if not stale_dir.exists():  # mapping with no files → just drop the row + resource
            await self._retire(stale)
            report.retired_empty.append(stale)
            return
        canonical_ulid = _ulid_of(canonical)
        await self._ensure_store(canonical)
        await self._roots.set(canonical, root)
        await self._move_label(stale, canonical)
        merge_store_dir(stale_dir, self._store_dir(canonical_ulid), tag=_ulid_of(stale)[:5])
        ref = build_store_ref_for(canonical, canonical_ulid, store_dir=self._store_dir)
        await self._reconciler.reconcile(store=ref, embedding=None, force=True)
        await self._retire(stale)
        report.merged_stores.append(stale)

    async def _ensure_store(self, store_name: str) -> None:
        try:
            await self._resources.get(ResourceRef(kind=KIND_MEMORY, name=store_name))
            return
        except ResourceNotFound:
            pass
        await self._resources.register(
            kind=KIND_MEMORY,
            name=store_name,
            config=MemoryStoreConfig().model_dump(mode="json"),
            actor="system",
        )

    async def _move_label(self, stale: str, canonical: str) -> None:
        label = await self._labels.get(stale)
        if label and not await self._labels.get(canonical):
            await self._labels.set(canonical, label)

    async def _retire(self, store_name: str) -> None:
        """Delete the stale store's resource (cascades to documents rows, the
        sqlite-vec table and the on-disk dir), then drop the two binding-table
        rows the generic teardown leaves behind."""
        with contextlib.suppress(ResourceNotFound):
            await self._resources.delete(
                ResourceRef(kind=KIND_MEMORY, name=store_name), actor="system"
            )
        await self._labels.clear(store_name)
        await self._roots.delete(store_name)


def _ulid_of(store_name: str) -> str:
    """The ULID encoded in a ``project-<ulid>`` store name."""
    return store_name[len("project-") :]
