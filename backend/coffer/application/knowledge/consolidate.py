"""One-time consolidation of duplicate per-project knowledge scopes.

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

from coffer.application.knowledge.scope import (
    GLOBAL_SCOPE_NAME,
    KIND_KNOWLEDGE,
    project_scope_name,
)
from coffer.application.knowledge.stores import store_ref_for
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.fs import atomic_write_bytes
from coffer.infrastructure.knowledge_scope.project_root_repo import ProjectRootRepo
from coffer.infrastructure.knowledge_scope.store_label_repo import StoreLabelRepo

_logger = logging.getLogger("coffer.memory.consolidate")

GitRootFn = Callable[[str], "Path | None"]
ProjectUlidFn = Callable[[str], str]
ScopeDirFn = Callable[[str], Path]


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
    """Merge every file under ``src`` into ``dst`` (additive). Returns the
    number of files merged/created.

    Everything under a scope dir is content someone wrote or uploaded — notes,
    documents, the originals and the archived revisions — so everything travels.

    Bytes, not text: ``.raw/`` holds the uploads exactly as they arrived, and a
    PDF or a .docx is not decodable UTF-8. Reading these as text used to raise
    ``UnicodeDecodeError`` on the first real upload, which ``run()`` swallowed
    into ``failed`` (the boot heal silently gave up on that project) and
    ``adopt()`` propagated (an ordinary write or recall failed outright).

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
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        body = path.read_bytes()
        if target.exists():
            if target.read_bytes() == body:
                continue  # already merged (idempotent retry / delta sweep)
            slot = _suffixed(target, tag, body)
            if slot is None:  # a suffixed copy from an earlier attempt
                continue
            target = slot
        atomic_write_bytes(target, body)
        merged += 1
    return merged


def _suffixed(target: Path, tag: str, body: bytes) -> Path | None:
    """A non-colliding sibling of ``target`` marked with the source ``tag``.

    Content-aware: a candidate that already exists WITH this exact ``body``
    means an earlier merge attempt landed it — return ``None`` (write nothing)
    instead of minting yet another copy."""
    candidate = target.with_name(f"{target.stem}--from-{tag}{target.suffix}")
    n = 2
    while candidate.exists():
        if candidate.read_bytes() == body:
            return None
        candidate = target.with_name(f"{target.stem}--from-{tag}-{n}{target.suffix}")
        n += 1
    return candidate


async def find_alias_holder(resources: ResourceService, project_id: str) -> str | None:
    """The store whose ``merged_identities`` lists ``project_id``.

    A merged-away identity must keep resolving to the store that absorbed it,
    or the next resolve would provision a fresh empty duplicate and undo the
    heal. Deterministic (stores scanned in name order) and self-excluding (a
    store never aliases its own identity). Shared by the resolver-redirect
    closure (``knowledge_wiring``), the boot pass's merge-reversal guard, and
    tests — one implementation, not three."""
    own = project_scope_name(project_id)
    for r in sorted(await resources.list(kind=KIND_KNOWLEDGE), key=lambda r: r.name):
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
        reconciler: KnowledgeReconciler,
        roots: ProjectRootRepo,
        labels: StoreLabelRepo,
        scope_dir: ScopeDirFn,
        git_root: GitRootFn,
        project_ulid: ProjectUlidFn,
    ) -> None:
        self._resources = resources
        self._reconciler = reconciler
        self._roots = roots
        self._labels = labels
        self._scope_dir = scope_dir
        self._git_root = git_root
        self._project_ulid = project_ulid
        # Serializes resolve-time adoptions (every remember/recall resolves).
        self._adopt_lock = asyncio.Lock()

    async def run(self) -> ConsolidationReport:
        report = ConsolidationReport()
        for scope_name, project_root in await self._roots.list_all():
            if scope_name == GLOBAL_SCOPE_NAME:
                continue
            root = self._git_root(project_root)
            if root is None:
                report.unresolvable.append(scope_name)
                continue
            canonical = project_scope_name(self._project_ulid(str(root)))
            if canonical != scope_name:
                canonical = await self._redirect_merged(canonical)
            if canonical == scope_name:
                if str(root) != project_root:  # normalise a drifted root string
                    await self._roots.set(scope_name, str(root))
                continue
            try:
                await self._merge_and_retire(scope_name, canonical, str(root), report)
            except Exception:  # best-effort: a failure leaves the stale store intact
                _logger.exception("consolidate.store.failed store=%s", scope_name)
                report.failed.append(scope_name)
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
        """Boot-pass guard: a canonical identity that was merged AWAY must not
        be re-provisioned — its alias holder IS the canonical
        store. Without this, a survivor whose recorded root re-resolves to a
        merged-away identity would be "healed" into a fresh empty duplicate at
        the next startup, reversing the user's merge and dropping every alias."""
        try:
            await self._resources.get(ResourceRef(KIND_KNOWLEDGE, canonical))
            return canonical  # the identity's own store exists — no redirect
        except ResourceNotFound:
            holder = await find_alias_holder(self._resources, _ulid_of(canonical))
            return holder or canonical

    async def adopt(self, stale: str, canonical: str, root: str) -> None:
        """Resolve-time adoption of a store under its portable name: identical
        semantics to the boot pass — additive merge, never
        a destructive move, retire only after the merge landed."""
        async with self._adopt_lock:
            await self._merge_and_retire(stale, canonical, root, ConsolidationReport())

    async def _record_aliases(
        self, target_res: object, source_res: object, *, actor: str
    ) -> list[str]:
        """Append the source's ULID + its own aliases to the target's
        ``merged_identities`` (order-preserving, deduped)."""
        target_cfg = KnowledgeConfig.model_validate(target_res.config)  # type: ignore[attr-defined]
        source_cfg = KnowledgeConfig.model_validate(source_res.config)  # type: ignore[attr-defined]
        aliases = list(target_cfg.merged_identities)
        for candidate in [_ulid_of(source_res.name), *source_cfg.merged_identities]:  # type: ignore[attr-defined]
            if candidate not in aliases:
                aliases.append(candidate)
        if aliases != target_cfg.merged_identities:
            new_cfg = target_cfg.model_copy(update={"merged_identities": aliases})
            await self._resources.update_config(
                ResourceRef(KIND_KNOWLEDGE, target_res.name),  # type: ignore[attr-defined]
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
        for r in await self._resources.list(kind=KIND_KNOWLEDGE):
            if r.name in keep or r.name == GLOBAL_SCOPE_NAME:
                continue
            ids = list((r.config or {}).get("merged_identities") or [])
            kept = [i for i in ids if i not in claimed]
            if kept == ids:
                continue
            cfg = KnowledgeConfig.model_validate(r.config)
            new_cfg = cfg.model_copy(update={"merged_identities": kept})
            await self._resources.update_config(
                ResourceRef(KIND_KNOWLEDGE, r.name),
                new_config=new_cfg.model_dump(mode="json"),
                actor=actor,
            )

    async def _merge_and_retire(
        self, stale: str, canonical: str, root: str, report: ConsolidationReport
    ) -> None:
        stale_dir = self._scope_dir(stale)
        if not stale_dir.exists():  # mapping with no files → just drop the row + resource
            await self._retire(stale)
            report.retired_empty.append(stale)
            return
        await self._ensure_store(canonical)
        await self._roots.set(canonical, root)
        await self._move_label(stale, canonical)
        # The retired identity (and any aliases it accumulated) must keep
        # resolving to the canonical store.
        with contextlib.suppress(ResourceNotFound):  # dir without a resource row
            canonical_res = await self._resources.get(ResourceRef(KIND_KNOWLEDGE, canonical))
            stale_res = await self._resources.get(ResourceRef(KIND_KNOWLEDGE, stale))
            await self._record_aliases(canonical_res, stale_res, actor="system")
        merge_store_dir(stale_dir, self._scope_dir(canonical), tag=_ulid_of(stale)[:5])
        ref = store_ref_for(canonical, scope_dir=self._scope_dir)
        await self._reconciler.reconcile(store=ref, embedding=None, force=True)
        await self._retire(stale)
        report.merged_stores.append(stale)

    async def _ensure_store(self, scope_name: str) -> None:
        try:
            await self._resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=scope_name))
            return
        except ResourceNotFound:
            pass
        with contextlib.suppress(ResourceAlreadyExists):  # concurrent adopters race
            await self._resources.register(
                kind=KIND_KNOWLEDGE,
                name=scope_name,
                config=KnowledgeConfig().model_dump(mode="json"),
                actor="system",
            )

    async def _move_label(self, stale: str, canonical: str) -> bool:
        label = await self._labels.get(stale)
        if label and not await self._labels.get(canonical):
            await self._labels.set(canonical, label)
            return True
        return False

    async def _retire(self, scope_name: str) -> None:
        """Delete the stale store's resource (cascades to documents rows, the
        sqlite-vec table and the on-disk dir), then drop the two binding-table
        rows the generic teardown leaves behind."""
        with contextlib.suppress(ResourceNotFound):
            await self._resources.delete(
                ResourceRef(kind=KIND_KNOWLEDGE, name=scope_name), actor="system"
            )
        await self._labels.clear(scope_name)
        await self._roots.delete(scope_name)


def _ulid_of(scope_name: str) -> str:
    """The ULID encoded in a ``project-<ulid>`` store name."""
    return scope_name[len("project-") :]
