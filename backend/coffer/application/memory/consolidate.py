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

import asyncio
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
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
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


@dataclass(frozen=True)
class MergeOutcome:
    """What an explicit user-triggered merge (FR-057) did."""

    target: str
    merged_files: int
    label_moved: bool
    root_moved: bool
    aliases: list[str]


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
    - A collision whose content is byte-identical is a no-op, so re-running the
      merge (a retry after a mid-merge failure, or the pre-retire delta sweep)
      never duplicates files.
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
        body = path.read_text(encoding="utf-8")
        if target.exists():
            if target.read_text(encoding="utf-8") == body:
                continue  # already merged (idempotent retry / delta sweep)
            slot = _suffixed(target, tag, body)
            if slot is None:  # a suffixed copy from an earlier attempt
                continue
            target = slot
        atomic_write_text(target, body)
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


def _suffixed(target: Path, tag: str, body: str) -> Path | None:
    """A non-colliding sibling of ``target`` marked with the source ``tag``.

    Content-aware: a candidate that already exists WITH this exact ``body``
    means an earlier merge attempt landed it — return ``None`` (write nothing)
    instead of minting yet another copy."""
    candidate = target.with_name(f"{target.stem}--from-{tag}{target.suffix}")
    n = 2
    while candidate.exists():
        if candidate.read_text(encoding="utf-8") == body:
            return None
        candidate = target.with_name(f"{target.stem}--from-{tag}-{n}{target.suffix}")
        n += 1
    return candidate


async def find_alias_holder(resources: ResourceService, project_id: str) -> str | None:
    """FR-058: the store whose ``merged_identities`` lists ``project_id``.

    Deterministic (stores scanned in name order) and self-excluding (a store
    never aliases its own identity). Shared by the resolver-redirect closure
    (``memory_wiring``), the boot pass's merge-reversal guard, and tests — one
    implementation, not three."""
    own = project_store_name(project_id)
    for r in sorted(await resources.list(kind=KIND_MEMORY), key=lambda r: r.name):
        if r.name == own:
            continue
        if project_id in ((r.config or {}).get("merged_identities") or []):
            return r.name
    return None


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
        # Serializes resolve-time adoptions (every remember/recall resolves).
        self._adopt_lock = asyncio.Lock()

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
            if canonical != store_name:
                canonical = await self._redirect_merged(canonical)
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

    async def _redirect_merged(self, canonical: str) -> str:
        """FR-058 guard for the boot pass: a canonical identity that was merged
        AWAY must not be re-provisioned — its alias holder IS the canonical
        store. Without this, a survivor whose recorded root re-resolves to a
        merged-away identity would be "healed" into a fresh empty duplicate at
        the next startup, reversing the user's merge and dropping every alias."""
        try:
            await self._resources.get(ResourceRef(KIND_MEMORY, canonical))
            return canonical  # the identity's own store exists — no redirect
        except ResourceNotFound:
            holder = await find_alias_holder(self._resources, _ulid_of(canonical))
            return holder or canonical

    async def adopt(self, stale: str, canonical: str, root: str) -> None:
        """Resolve-time adoption of a store under its portable name (spec 007
        FR-004a): identical semantics to the boot pass — additive merge, never
        a destructive move, retire only after the merge landed."""
        async with self._adopt_lock:
            await self._merge_and_retire(stale, canonical, root, ConsolidationReport())

    async def merge(self, source: str, target: str, *, actor: str = "user") -> MergeOutcome:
        """Explicit user-triggered merge of two existing project stores
        (spec 007 amendment 2026-07-10, FR-057/FR-058).

        Unlike the root-driven ``_merge_and_retire``, both stores already
        exist and the target keeps its own label/root when it has them; the
        source's project ULID (plus its own aliases, transitively) is recorded
        in the target's ``merged_identities`` so a future resolve of the
        merged-away identity lands on the survivor instead of re-provisioning
        an empty duplicate. Serialized with resolve-time adoption; fact writes
        do NOT hold this lock, so a delta sweep right before retirement
        re-merges anything written into the source mid-merge."""
        async with self._adopt_lock:
            target_res = await self._resources.get(ResourceRef(KIND_MEMORY, target))
            source_res = await self._resources.get(ResourceRef(KIND_MEMORY, source))
            source_dir = self._store_dir(_ulid_of(source))
            target_dir = self._store_dir(_ulid_of(target))
            tag = _ulid_of(source)[:5]
            label_moved = await self._move_label(source, target)
            root_moved = False
            source_root = await self._roots.get(source)
            if source_root and not await self._roots.get(target):
                await self._roots.set(target, source_root)
                root_moved = True
            merged = merge_store_dir(source_dir, target_dir, tag=tag)
            aliases = await self._record_aliases(target_res, source_res, actor=actor)
            ref = build_store_ref_for(target, _ulid_of(target), store_dir=self._store_dir)
            await self._reconciler.reconcile(store=ref, embedding=None, force=True)
            # Delta sweep: pick up facts written into the source during the
            # merge's awaits (content-idempotent, so already-merged files no-op).
            delta = merge_store_dir(source_dir, target_dir, tag=tag)
            if delta:
                merged += delta
                await self._reconciler.reconcile(store=ref, embedding=None, force=False)
            await self._retire(source)
            return MergeOutcome(
                target=target,
                merged_files=merged,
                label_moved=label_moved,
                root_moved=root_moved,
                aliases=aliases,
            )

    async def _record_aliases(
        self, target_res: object, source_res: object, *, actor: str
    ) -> list[str]:
        """FR-058: append the source's ULID + its own aliases to the target's
        ``merged_identities`` (order-preserving, deduped)."""
        target_cfg = MemoryStoreConfig.model_validate(target_res.config)  # type: ignore[attr-defined]
        source_cfg = MemoryStoreConfig.model_validate(source_res.config)  # type: ignore[attr-defined]
        aliases = list(target_cfg.merged_identities)
        for candidate in [_ulid_of(source_res.name), *source_cfg.merged_identities]:  # type: ignore[attr-defined]
            if candidate not in aliases:
                aliases.append(candidate)
        if aliases != target_cfg.merged_identities:
            new_cfg = target_cfg.model_copy(update={"merged_identities": aliases})
            await self._resources.update_config(
                ResourceRef(KIND_MEMORY, target_res.name),  # type: ignore[attr-defined]
                new_config=new_cfg.model_dump(mode="json"),
                actor=actor,
            )
        await self._strip_alias_claims(
            claimed=set(aliases),
            keep=(target_res.name, source_res.name),  # type: ignore[attr-defined]
            actor=actor,
        )
        return aliases

    async def _strip_alias_claims(
        self, *, claimed: set[str], keep: tuple[str, str], actor: str
    ) -> None:
        """Exactly one live holder per merged identity: drop every id the new
        holder now claims from every OTHER store's ``merged_identities`` (a
        stale claim would make the resolver redirect ambiguous)."""
        for r in await self._resources.list(kind=KIND_MEMORY):
            if r.name in keep or r.name == GLOBAL_STORE_NAME:
                continue
            ids = list((r.config or {}).get("merged_identities") or [])
            kept = [i for i in ids if i not in claimed]
            if kept == ids:
                continue
            cfg = MemoryStoreConfig.model_validate(r.config)
            new_cfg = cfg.model_copy(update={"merged_identities": kept})
            await self._resources.update_config(
                ResourceRef(KIND_MEMORY, r.name),
                new_config=new_cfg.model_dump(mode="json"),
                actor=actor,
            )

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
        # FR-058 also holds for boot/adoption merges: the retired identity (and
        # any aliases it accumulated) must keep resolving to the canonical store.
        with contextlib.suppress(ResourceNotFound):  # dir without a resource row
            canonical_res = await self._resources.get(ResourceRef(KIND_MEMORY, canonical))
            stale_res = await self._resources.get(ResourceRef(KIND_MEMORY, stale))
            await self._record_aliases(canonical_res, stale_res, actor="system")
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
        with contextlib.suppress(ResourceAlreadyExists):  # concurrent adopters race
            await self._resources.register(
                kind=KIND_MEMORY,
                name=store_name,
                config=MemoryStoreConfig().model_dump(mode="json"),
                actor="system",
            )

    async def _move_label(self, stale: str, canonical: str) -> bool:
        label = await self._labels.get(stale)
        if label and not await self._labels.get(canonical):
            await self._labels.set(canonical, label)
            return True
        return False

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
