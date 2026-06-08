"""MemoryService — orchestration for the ``memory`` kind (spec 007).

Memory is the writable face of the shared knowledge substrate: per-fact markdown
files under ``~/.coffer/memory/{global,projects/<ulid>}/`` are the source of
truth, with a regenerated ``MEMORY.md`` index. No LLM at write time — the writer
(agent or user) hands Coffer a clean fact. Retrieval reuses the KB engine with
lazy reindex-on-read.

Composes ``ResourceService`` (store-as-Resource), the unified ``DocumentRepo``,
the ``ScopeResolver`` (cwd → store), the ``MemoryReconciler``, the shared
``KnowledgeRetrieval`` facade, ``AuditService``, and the per-fact file I/O. The
mutation pipeline (``writes``), recall (``recall``), scan reads (``queries``),
store-name ⇄ scope plumbing (``stores``), and pure helpers (``service_helpers``)
live in sibling modules to keep this file focused.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.queries import (
    find_fact_store,
    list_facts_in_dir,
    read_fact,
    store_metrics,
)
from coffer.application.memory.recall import (
    RecallDeps,
    RecallScope,
    recall_across,
    recall_in_store_scoped,
)
from coffer.application.memory.scope import GLOBAL_STORE_NAME, ScopeResolver
from coffer.application.memory.stores import (
    build_store_ref_for,
    project_resolved_for_store,
    store_name_for,
)
from coffer.application.memory.sync import MemoryReconciler
from coffer.application.memory.writes import (
    WriteDeps,
    add_new_fact,
    clear_all_facts,
    remove_fact,
    update_existing_fact,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import MemoryStoreNotFound
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import MemoryHit, RetrievalMode
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import Actor, MemoryFact
from coffer.domain.memory.scope import MemoryScope, ResolvedScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.memory.files import (
    FactFile,
    read_fact_file,
    scan_store_dir,
)

#: Injected path helpers (the composition root passes the infrastructure
#: functions, so the service does not import ``infrastructure.knowledge.paths``).
StoreDirFn = Callable[[str], Path]
FactPathFn = Callable[[Path, str], Path]
#: Post-write hook: ``store_name -> awaitable`` (re-render native projections).
OnChangeFn = Callable[[str], Awaitable[None]]


class MemoryService:
    """Application service for memory operations."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        documents: MemoryDocumentRepo,
        scope_resolver: ScopeResolver,
        reconciler: MemoryReconciler,
        retrieval: KnowledgeRetrieval,
        audit: AuditService,
        store_dir: StoreDirFn,
        fact_path: FactPathFn,
        on_change: OnChangeFn | None = None,
    ) -> None:
        self._resources = resource_service
        self._documents = documents
        self._scope = scope_resolver
        self._reconciler = reconciler
        self._retrieval = retrieval
        self._audit = audit
        self._store_dir = store_dir
        self._fact_path = fact_path
        # Cross-kind hook wired at the composition root (the memory kind may not
        # import the agent kind): re-render a store's native projection after a
        # write so an agent's symlinked / managed-block view stays current.
        self._on_change = on_change
        # Bundle the collaborators the write + recall orchestrators need.
        store_ref_fn = partial(build_store_ref_for, store_dir=store_dir)
        self._writes = WriteDeps(
            audit=audit,
            reconciler=reconciler,
            notify=self._notify_change,
            fact_path=fact_path,
            store_ref=store_ref_fn,
        )
        self._recall = RecallDeps(
            reconciler=reconciler,
            retrieval=retrieval,
            get_config=self.get_store_config,
            store_name_for=store_name_for,
            store_ref=store_ref_fn,
        )

    def set_on_change(self, hook: OnChangeFn | None) -> None:
        """Install/replace the post-write change hook (composition root)."""
        self._on_change = hook

    async def _notify_change(self, store_name: str) -> None:
        if self._on_change is None:
            return
        with contextlib.suppress(Exception):
            await self._on_change(store_name)

    # ----- scope -----

    async def resolve_scope(self, *, scope: MemoryScope, cwd: str | None) -> ResolvedScope:
        return await self._scope.resolve(scope=scope, cwd=cwd)

    async def ensure_store(self, store_name: str) -> None:
        """Provision a store's Resource if absent (surfaces address stores by
        name). The global store auto-provisions on first REST access; a
        ``project-<ulid>`` store is provisioned directly (no cwd needed)."""
        ref = ResourceRef(kind=KIND_MEMORY, name=store_name)
        try:
            await self._resources.get(ref)
            return
        except Exception:
            pass
        if store_name == GLOBAL_STORE_NAME:
            await self.resolve_scope(scope=MemoryScope.GLOBAL, cwd=None)
            return
        await self._resources.register(
            kind=KIND_MEMORY,
            name=store_name,
            config=MemoryStoreConfig().model_dump(mode="json"),
            actor="system",
        )

    async def get_store_config(self, store_name: str) -> MemoryStoreConfig:
        ref = ResourceRef(kind=KIND_MEMORY, name=store_name)
        try:
            resource = await self._resources.get(ref)
        except Exception as exc:
            raise MemoryStoreNotFound(store_name) from exc
        return MemoryStoreConfig.model_validate(resource.config)

    # ----- writes -----

    async def add_fact(
        self,
        *,
        scope: MemoryScope,
        cwd: str | None,
        name: str,
        description: str,
        body: str,
        actor: Actor,
        type: str | None = None,
        origin_session_id: str | None = None,
    ) -> MemoryFact:
        """Write a fact file → regenerate ``MEMORY.md`` → index → audit (no LLM)."""
        resolved = await self.resolve_scope(scope=scope, cwd=cwd)
        store_name = store_name_for(resolved)
        config = await self.get_store_config(store_name)
        return await add_new_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            config=config,
            name=name,
            description=description,
            body=body,
            actor=actor,
            type=type,
            origin_session_id=origin_session_id,
        )

    async def add_fact_to_store(
        self,
        *,
        store_name: str,
        name: str,
        description: str,
        body: str,
        actor: Actor,
        type: str | None = None,
        origin_session_id: str | None = None,
    ) -> MemoryFact:
        """Write a fact to a store by name (REST face: store-scoped, no cwd)."""
        config = await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        return await add_new_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            config=config,
            name=name,
            description=description,
            body=body,
            actor=actor,
            type=type,
            origin_session_id=origin_session_id,
        )

    async def update_fact(
        self,
        *,
        store_name: str,
        fact_id: str,
        new_body: str,
        actor: str,
        new_name: str | None = None,
        new_description: str | None = None,
        new_type: str | None = None,
    ) -> MemoryFact:
        """Edit a fact's body (and optionally name/description/type) → regenerate
        ``MEMORY.md`` → reindex → audit. ``None`` for an optional field leaves it
        unchanged (the agent-facing ``update_memory`` tool passes body only)."""
        config = await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        ff = self._read_fact(resolved.store_dir, fact_id)
        return await update_existing_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            config=config,
            existing=ff,
            new_body=new_body,
            actor=actor,
            new_name=new_name,
            new_description=new_description,
            new_type=new_type,
        )

    async def delete_fact(self, *, store_name: str, fact_id: str, actor: str) -> None:
        """Delete a fact file → drop index rows → regenerate ``MEMORY.md`` → audit."""
        await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        ff = self._read_fact(resolved.store_dir, fact_id)
        await remove_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            existing=ff,
            actor=actor,
        )

    # ``forget`` is the agent-facing alias of delete.
    forget = delete_fact

    async def clear(self, *, store_name: str, actor: str) -> int:
        """Remove every fact in a store; keep the store Resource."""
        await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        scan = scan_store_dir(resolved.store_dir)
        return await clear_all_facts(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            files=scan.files,
            actor=actor,
        )

    # ----- reads -----

    async def recall(
        self,
        *,
        cwd: str | None,
        query: str,
        scope: MemoryScope | None = None,
        top_k: int = 5,
        mode: RetrievalMode | None = None,
    ) -> list[MemoryHit]:
        """Lazy reindex-on-read recall, spanning project + global by default."""
        if scope is None:
            resolved_scopes = await self._scope.resolve_recall_scopes(cwd=cwd)
        else:
            resolved_scopes = [await self.resolve_scope(scope=scope, cwd=cwd)]
        return await recall_across(
            self._recall,
            resolved_scopes=resolved_scopes,
            query=query,
            top_k=top_k,
            mode=mode,
        )

    async def recall_in_store(
        self,
        *,
        store_name: str,
        query: str,
        top_k: int = 5,
        mode: RetrievalMode | None = None,
        scope: RecallScope = "project",
    ) -> tuple[list[MemoryHit], RetrievalMode, bool]:
        """Recall within a named store, honouring ``scope`` (finding #5).

        ``project`` spans the named store only; ``both``/``global`` also fold in
        the global store. Returns ``(hits, effective_mode, fallback)``."""
        return await recall_in_store_scoped(
            self._recall,
            store_name=store_name,
            scope=scope,
            query=query,
            top_k=top_k,
            mode=mode,
            get_config=self.get_store_config,
            resolved_for=self._resolved_for_store,
        )

    async def list_facts(
        self, *, store_name: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[MemoryFact], int]:
        await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        return list_facts_in_dir(resolved.store_dir, limit=limit, offset=offset)

    async def get_fact(self, *, store_name: str, fact_id: str) -> MemoryFact:
        await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        return self._read_fact(resolved.store_dir, fact_id).fact

    async def resolved_store(self, store_name: str) -> ResolvedScope:
        """Public ``ResolvedScope`` for an existing store (scope + store_dir).

        Surfaces use it to report a store's scope / project_id and to locate the
        on-disk store directory (e.g. for projection). Validates the store
        exists first."""
        await self.get_store_config(store_name)
        return await self._resolved_for_store(store_name)

    async def get_fact_with_path(self, *, store_name: str, fact_id: str) -> tuple[MemoryFact, str]:
        """A fact plus the absolute path of its canonical markdown file."""
        await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        ff = self._read_fact(resolved.store_dir, fact_id)
        return ff.fact, str(ff.path)

    async def find_fact_store(self, *, cwd: str | None, fact_id: str) -> str:
        """Return the store name holding ``fact_id`` across the recall scopes
        (project then global). Raises ``MemoryNotFound`` if absent everywhere.
        Used by the agent ``update_memory`` / ``forget`` tools (id-only)."""
        scopes = await self._scope.resolve_recall_scopes(cwd=cwd)
        return find_fact_store(scopes, fact_id, store_name_for)

    async def metrics(self, *, store_name: str) -> dict[str, object]:
        config = await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        return await store_metrics(resolved.store_dir, config)

    # ----- on_delete kind hook -----

    async def cleanup_store(self, store_name: str) -> None:
        config = await self.get_store_config(store_name)
        resolved = await self._resolved_for_store(store_name)
        await self._documents.delete_resource(KIND_MEMORY, store_name)
        # Drop the per-store sqlite-vec table too (lives outside the async
        # session → leaks across a same-name re-create otherwise — finding #6).
        dims = config.embedding_dimensions if config.vector_enabled else None
        with contextlib.suppress(Exception):
            await self._retrieval.drop_store(
                self._recall.store_ref(store_name, resolved.project_id), dimensions=dims
            )
        if resolved.store_dir.exists():
            await asyncio.to_thread(shutil.rmtree, resolved.store_dir, ignore_errors=True)

    # ----- internals -----

    async def _resolved_for_store(self, store_name: str) -> ResolvedScope:
        """Recover a ``ResolvedScope`` for an existing store by name (reads the
        store's project_id off any of its rows, falling back to global)."""
        if store_name == GLOBAL_STORE_NAME:
            return await self.resolve_scope(scope=MemoryScope.GLOBAL, cwd=None)
        return project_resolved_for_store(store_name, self._store_dir)

    def _read_fact(self, store_dir: Path, fact_id: str) -> FactFile:
        return read_fact(store_dir, fact_id)


# Re-export the parser for callers that read a fact file directly (e.g. tests).
__all__ = ["MemoryService", "read_fact_file"]
