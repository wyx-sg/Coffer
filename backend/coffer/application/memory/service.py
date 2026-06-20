"""MemoryService — orchestration for the ``memory`` kind (spec 007).

Memory is the writable face of the shared knowledge substrate: per-item markdown
files under each store's ``knowledge/`` lane are the source of truth (no derived
index). No LLM at write time; retrieval reuses the KB engine with lazy
reindex-on-read. Mutation (``writes``), recall, scan reads (``queries``), admin,
scope plumbing (``stores``) and helpers live in sibling modules to keep this
file focused.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.memory import admin
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.queries import (
    find_fact_store,
    list_fact_files_in_dir,
    read_fact,
    store_metrics,
)
from coffer.application.memory.recall import (
    RecallDeps,
    RecallScope,
    recall_in_store_scoped,
    recall_spanning,
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

_logger = logging.getLogger(__name__)

#: Injected path helpers (the composition root passes the infrastructure
#: functions, so the service does not import ``infrastructure.knowledge.paths``).
StoreDirFn = Callable[[str], Path]
#: Post-write hook: ``store_name -> awaitable`` (generic post-write extension).
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
        on_change: OnChangeFn | None = None,
        embedding_resolver: EmbeddingResolver = no_embedding,
    ) -> None:
        self._resources = resource_service
        self._documents = documents
        self._scope = scope_resolver
        self._reconciler = reconciler
        self._retrieval = retrieval
        self._audit = audit
        self._store_dir = store_dir
        self._resolve_embedding = embedding_resolver  # global embedding config
        self._on_change = on_change  # generic post-write hook (no consumer today)
        # Bundle the collaborators the write + recall orchestrators need.
        store_ref_fn = partial(build_store_ref_for, store_dir=store_dir)
        self._writes = WriteDeps(
            audit=audit,
            reconciler=reconciler,
            notify=self._notify_change,
            store_ref=store_ref_fn,
            embedding_resolver=embedding_resolver,
        )
        self._recall = RecallDeps(
            reconciler=reconciler,
            retrieval=retrieval,
            documents=documents,
            get_config=self.get_store_config,
            store_name_for=store_name_for,
            store_ref=store_ref_fn,
            embedding_resolver=embedding_resolver,
        )

    def set_on_change(self, hook: OnChangeFn | None) -> None:
        """Install/replace the post-write change hook (composition root)."""
        self._on_change = hook

    async def _notify_change(self, store_name: str) -> None:
        if self._on_change is None:
            return
        try:
            await self._on_change(store_name)
        except Exception:
            # The write itself succeeded; a post-write hook failure must not
            # surface to the caller, so log loudly instead of raising.
            _logger.warning(
                "memory.on_change.hook_failed",
                extra={"store": store_name},
                exc_info=True,
            )

    # ----- scope -----

    async def resolve_scope(self, *, scope: MemoryScope, cwd: str | None) -> ResolvedScope:
        return await self._scope.resolve(scope=scope, cwd=cwd)

    async def ensure_store(self, store_name: str) -> None:
        """Provision a store's Resource if absent; 404 for arbitrary names."""
        await admin.ensure_store(
            resources=self._resources,
            provision_global=partial(self.resolve_scope, scope=MemoryScope.GLOBAL, cwd=None),
            store_name=store_name,
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
        """Write a fact file to ``knowledge/inbox/`` → index → audit (no LLM)."""
        resolved = await self.resolve_scope(scope=scope, cwd=cwd)
        return await self._add(
            resolved,
            store_name_for(resolved),
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
        resolved = await self._resolved_for_store(store_name)
        return await self._add(
            resolved,
            store_name,
            name=name,
            description=description,
            body=body,
            actor=actor,
            type=type,
            origin_session_id=origin_session_id,
        )

    async def _add(
        self,
        resolved: ResolvedScope,
        store_name: str,
        **fact_fields: object,
    ) -> MemoryFact:
        config = await self.get_store_config(store_name)
        return await add_new_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            config=config,
            **fact_fields,  # type: ignore[arg-type]
        )

    async def update_fact(self, *, store_name: str, fact_id: str, **changes: object) -> MemoryFact:
        """Edit a fact (``new_body`` + ``actor`` required; ``None`` optional
        fields stay unchanged) → reindex → audit."""
        resolved, ff = await self._store_fact(store_name, fact_id)
        config = await self.get_store_config(store_name)
        return await update_existing_fact(
            deps=self._writes,
            resolved=resolved,
            store_name=store_name,
            config=config,
            existing=ff,
            **changes,  # type: ignore[arg-type]
        )

    async def delete_fact(self, *, store_name: str, fact_id: str, actor: str) -> None:
        """Delete a fact file → drop index rows → audit."""
        resolved, ff = await self._store_fact(store_name, fact_id)
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
        scan = await asyncio.to_thread(scan_store_dir, resolved.store_dir)
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
    ) -> tuple[list[MemoryHit], bool]:
        """Recall spanning project + global; returns ``(hits, fallback)``."""
        return await recall_spanning(
            self._recall,
            resolver=self._scope,
            cwd=cwd,
            query=query,
            scope=scope,
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

        Returns ``(hits, effective_mode, fallback)``."""
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
        files, total = await self.list_fact_files(store_name=store_name, limit=limit, offset=offset)
        return [ff.fact for ff in files], total

    async def list_fact_files(
        self, *, store_name: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[FactFile], int]:
        """One directory scan serving fact + path per row (no per-fact rescans)."""
        resolved = await self.resolved_store(store_name)
        return await asyncio.to_thread(
            list_fact_files_in_dir, resolved.store_dir, limit=limit, offset=offset
        )

    async def get_fact(self, *, store_name: str, fact_id: str) -> MemoryFact:
        return (await self._store_fact(store_name, fact_id))[1].fact

    async def resolved_store(self, store_name: str) -> ResolvedScope:
        """Public ``ResolvedScope`` for an EXISTING store (validates first)."""
        await self.get_store_config(store_name)
        return await self._resolved_for_store(store_name)

    async def get_fact_with_path(self, *, store_name: str, fact_id: str) -> tuple[MemoryFact, str]:
        """A fact plus the absolute path of its canonical markdown file."""
        _resolved, ff = await self._store_fact(store_name, fact_id)
        return ff.fact, str(ff.path)

    async def find_fact_store(self, *, cwd: str | None, fact_id: str) -> str:
        """Return the store name holding ``fact_id`` across the recall scopes
        (project then global). Raises ``MemoryNotFound`` if absent everywhere.
        Used by the REST/CLI edit/delete-by-id paths."""
        scopes = await self._scope.resolve_recall_scopes(cwd=cwd)
        return await asyncio.to_thread(find_fact_store, scopes, fact_id, store_name_for)

    async def fact_count(self, *, store_name: str) -> int:
        """Cheap indexed fact count for the list path (no ``scan_store_dir`` parse
        / ``du_bytes`` walk; staleness closes on the next recall/reconcile)."""
        return await self._documents.count_documents(KIND_MEMORY, store_name)

    async def metrics(self, *, store_name: str) -> dict[str, object]:
        config = await self.get_store_config(store_name)
        return await store_metrics((await self._resolved_for_store(store_name)).store_dir, config)

    # ----- on_update_config / on_delete kind hooks -----

    async def reindex_store(
        self, *, store_name: str, config: MemoryStoreConfig | None = None
    ) -> None:
        """Force-rebuild a store's index (see ``admin.reindex_store``)."""
        await admin.reindex_store(
            get_config=self.get_store_config,
            resolved_for=self._resolved_for_store,
            store_ref=self._recall.store_ref,
            reconciler=self._reconciler,
            store_name=store_name,
            config=config,
            embedding_resolver=self._resolve_embedding,
        )

    async def cleanup_store(self, store_name: str) -> None:
        """Drop a store's rows, vec table and on-disk dir (on_delete hook)."""
        await admin.cleanup_store(
            get_config=self.get_store_config,
            resolved_for=self._resolved_for_store,
            store_ref=self._recall.store_ref,
            documents=self._documents,
            retrieval=self._retrieval,
            reconciler=self._reconciler,
            store_name=store_name,
        )

    # ----- internals -----

    async def _resolved_for_store(self, store_name: str) -> ResolvedScope:
        """Recover a ``ResolvedScope`` for an existing store by name (reads the
        store's project_id off any of its rows, falling back to global)."""
        if store_name == GLOBAL_STORE_NAME:
            return await self.resolve_scope(scope=MemoryScope.GLOBAL, cwd=None)
        return project_resolved_for_store(store_name, self._store_dir)

    async def _store_fact(self, store_name: str, fact_id: str) -> tuple[ResolvedScope, FactFile]:
        """Validate the store, resolve it, and read one fact off-loop."""
        resolved = await self.resolved_store(store_name)
        ff = await asyncio.to_thread(read_fact, resolved.store_dir, fact_id)
        return resolved, ff


# Re-export the parser for callers that read a fact file directly (e.g. tests).
__all__ = ["MemoryService", "read_fact_file"]
