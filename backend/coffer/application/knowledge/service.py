"""KnowledgeService — orchestration for the one ``knowledge`` kind.

One facade over three scopes (``global``, ``project-<ULID>``, a named
collection) and the two kinds of material a person actually distinguishes:
**notes**, what an agent or the user wrote, in ``notes/``, and **documents**,
what someone uploaded, in ``docs/``. Markdown on disk is the source of truth
either way; no LLM at write time — the tidy pass does its work later, on what
is already filed.

The ingestion half lives in ``documents.DocumentOps`` — a mixin, not a second
service, so that both halves stay under the project's file-size ceiling while
callers still see one object. Sibling modules handle writes, recall, admin,
scope, and reconcile.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge import admin, session_context
from coffer.application.knowledge.documents import DocumentOps
from coffer.application.knowledge.entry_reads import EntryReads
from coffer.application.knowledge.pipeline import IngestPipeline
from coffer.application.knowledge.pipeline_helpers import KnowledgePaths
from coffer.application.knowledge.ports import DocumentRepoPort
from coffer.application.knowledge.queries import read_fact
from coffer.application.knowledge.recall import (
    RecallDeps,
    RecallScope,
    recall_in_store_scoped,
    recall_spanning,
)
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge.scope import GLOBAL_SCOPE_NAME, ScopeResolver
from coffer.application.knowledge.stores import (
    build_store_ref_for,
    project_resolved_for_scope,
    scope_name_for,
    store_ref_for,
)
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.application.knowledge.writes import (
    WriteDeps,
    add_new_fact,
    clear_all_facts,
    remove_fact,
    update_existing_fact,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import MemoryStoreNotFound
from coffer.domain.knowledge.converter import MarkdownConverter
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.entry import Actor, KnowledgeEntry
from coffer.domain.knowledge.retrieval import MemoryHit, RetrievalMode, StoreRef
from coffer.domain.knowledge.scope import KnowledgeScope, ResolvedScope, scope_kind_of
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge_scope.files import (
    FactFile,
    read_fact_file,
    scan_scope_dir,
)

ScopeDirFn = Callable[[str], Path]
OnChangeFn = Callable[[str], Awaitable[None]]


class KnowledgeService(EntryReads, DocumentOps):
    """Application service for every knowledge operation in a scope."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        documents: DocumentRepoPort,
        scope_resolver: ScopeResolver,
        reconciler: KnowledgeReconciler,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
        converters: MarkdownConverter,
        audit: AuditService,
        paths: KnowledgePaths,
        scope_dir: ScopeDirFn,
        on_change: OnChangeFn | None = None,
        embedding_resolver: EmbeddingResolver = no_embedding,
    ) -> None:
        self._resources = resource_service
        self._documents = documents
        self._scope = scope_resolver
        self._reconciler = reconciler
        self._retrieval = retrieval
        self._audit = audit
        self._paths = paths
        self._scope_dir = scope_dir
        self._resolve_embedding = embedding_resolver
        self._on_change = on_change
        self._pipeline = IngestPipeline(
            documents=documents,
            converters=converters,
            retrieval=retrieval,
            reindexer=reindexer,
            paths=paths,
            embedding_resolver=embedding_resolver,
        )
        store_ref_fn = partial(build_store_ref_for, scope_dir=scope_dir)
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
            get_config=self.get_config,
            scope_name_for=scope_name_for,
            store_ref=store_ref_fn,
            embedding_resolver=embedding_resolver,
        )

    def set_on_change(self, hook: OnChangeFn | None) -> None:
        """Install/replace the post-write change hook (composition root)."""
        self._on_change = hook

    async def _notify_change(self, scope_name: str) -> None:
        await session_context.notify_change(self._on_change, scope_name)

    # ----- scope -----

    async def resolve_scope(
        self, *, scope: KnowledgeScope, cwd: str | None, name: str | None = None
    ) -> ResolvedScope:
        """Resolve a scope. ``name`` is required for ``KnowledgeScope.NAMED``."""
        return await self._scope.resolve(scope=scope, cwd=cwd, name=name)

    def _store_ref(self, scope_name: str) -> StoreRef:
        """The retrieval ``StoreRef`` for a scope (the ingestion half's hook)."""
        return store_ref_for(scope_name, scope_dir=self._scope_dir)

    async def ensure_scope(self, scope_name: str) -> None:
        """Provision an auto-scope's Resource if absent; 404 for other names."""
        await admin.ensure_scope(
            resources=self._resources,
            provision_global=partial(self.resolve_scope, scope=KnowledgeScope.GLOBAL, cwd=None),
            scope_name=scope_name,
        )

    async def get_config(self, scope_name: str) -> KnowledgeConfig:
        ref = ResourceRef(kind=KIND_KNOWLEDGE, name=scope_name)
        try:
            resource = await self._resources.get(ref)
        except Exception as exc:
            raise MemoryStoreNotFound(scope_name) from exc
        return KnowledgeConfig.model_validate(resource.config)

    # ----- writes -----

    async def add_fact(
        self,
        *,
        scope: KnowledgeScope,
        cwd: str | None,
        title: str,
        description: str,
        body: str,
        actor: Actor,
        origin_session_id: str | None = None,
        max_entry_chars: int | None = None,
    ) -> KnowledgeEntry:
        """Write a note to ``notes/`` → index (no LLM).
        ``max_entry_chars`` overrides the store length limit (a trusted import raises it)."""
        resolved = await self.resolve_scope(scope=scope, cwd=cwd)
        return await self._add(
            resolved,
            scope_name_for(resolved),
            max_entry_chars=max_entry_chars,
            title=title,
            description=description,
            body=body,
            actor=actor,
            origin_session_id=origin_session_id,
        )

    async def add_fact_to_scope(
        self,
        *,
        scope_name: str,
        title: str,
        description: str,
        body: str,
        actor: Actor,
        origin_session_id: str | None = None,
    ) -> KnowledgeEntry:
        """Write a fact to a store by name (REST face: store-scoped, no cwd)."""
        resolved = await self._resolved_for_scope(scope_name)
        return await self._add(
            resolved,
            scope_name,
            title=title,
            description=description,
            body=body,
            actor=actor,
            origin_session_id=origin_session_id,
        )

    async def _add(
        self,
        resolved: ResolvedScope,
        scope_name: str,
        *,
        max_entry_chars: int | None = None,
        **fact_fields: object,
    ) -> KnowledgeEntry:
        config = await self.get_config(scope_name)
        if max_entry_chars is not None:
            config = config.model_copy(update={"max_entry_chars": max_entry_chars})
        return await add_new_fact(
            deps=self._writes,
            resolved=resolved,
            scope_name=scope_name,
            config=config,
            **fact_fields,  # type: ignore[arg-type]
        )

    async def update_fact(
        self, *, scope_name: str, fact_id: str, **changes: object
    ) -> KnowledgeEntry:
        """Edit a fact (``new_body`` + ``actor`` required) → reindex."""
        resolved, ff = await self._store_fact(scope_name, fact_id)
        config = await self.get_config(scope_name)
        return await update_existing_fact(
            deps=self._writes,
            resolved=resolved,
            scope_name=scope_name,
            config=config,
            existing=ff,
            **changes,  # type: ignore[arg-type]
        )

    async def delete_fact(self, *, scope_name: str, fact_id: str, actor: str) -> None:
        """Delete a fact file → drop index rows → audit."""
        resolved, ff = await self._store_fact(scope_name, fact_id)
        await remove_fact(
            deps=self._writes,
            resolved=resolved,
            scope_name=scope_name,
            existing=ff,
            actor=actor,
        )

    forget = delete_fact  # agent-facing alias of delete

    async def clear(self, *, scope_name: str, actor: str) -> int:
        """Remove every note in a store; keep the store Resource."""
        await self.get_config(scope_name)
        resolved = await self._resolved_for_scope(scope_name)
        scan = await asyncio.to_thread(scan_scope_dir, resolved.store_dir)
        return await clear_all_facts(
            deps=self._writes,
            resolved=resolved,
            scope_name=scope_name,
            files=scan.files,
            actor=actor,
        )

    # ----- reads -----

    async def recall(
        self,
        *,
        cwd: str | None,
        query: str,
        scope: KnowledgeScope | None = None,
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

    async def recall_in_scope(
        self,
        *,
        scope_name: str,
        query: str,
        top_k: int = 5,
        mode: RetrievalMode | None = None,
        scope: RecallScope = "project",
    ) -> tuple[list[MemoryHit], RetrievalMode, bool]:
        """Recall within a named store, honouring ``scope``; returns
        ``(hits, effective_mode, fallback)``."""
        return await recall_in_store_scoped(
            self._recall,
            scope_name=scope_name,
            scope=scope,
            query=query,
            top_k=top_k,
            mode=mode,
            get_config=self.get_config,
            resolved_for=self._resolved_for_scope,
        )

    # ----- on_update_config / on_delete kind hooks -----

    async def reindex_scope(
        self, *, scope_name: str, config: KnowledgeConfig | None = None
    ) -> None:
        """Force-rebuild a scope's index — both lanes (see ``admin``)."""
        await admin.reindex_scope(
            get_config=self.get_config,
            resolved_for=self._resolved_for_scope,
            store_ref=self._recall.store_ref,
            reconciler=self._reconciler,
            scope_name=scope_name,
            config=config,
            embedding_resolver=self._resolve_embedding,
        )
        await self.reindex_documents(
            scope_name=scope_name, actor="system", config=config, force=True
        )

    async def cleanup_scope(self, scope_name: str) -> None:
        """Drop a scope's rows, vec table and on-disk dir (on_delete hook)."""
        self._pipeline.fingerprint_cache.pop(scope_name, None)
        await admin.cleanup_scope(
            get_config=self.get_config,
            resolved_for=self._resolved_for_scope,
            store_ref=self._recall.store_ref,
            documents=self._documents,
            retrieval=self._retrieval,
            reconciler=self._reconciler,
            scope_name=scope_name,
        )

    # ----- internals -----

    async def _resolved_for_scope(self, scope_name: str) -> ResolvedScope:
        """Recover a ``ResolvedScope`` for an existing scope by name.

        ``global`` provisions on the way through; a ``project-<ulid>`` name
        carries its own ULID; anything else is a named collection, which must
        already exist."""
        if scope_name == GLOBAL_SCOPE_NAME:
            return await self.resolve_scope(scope=KnowledgeScope.GLOBAL, cwd=None)
        if scope_kind_of(scope_name) is KnowledgeScope.NAMED:
            return await self._scope.resolve_named(scope_name)
        return project_resolved_for_scope(scope_name, self._scope_dir)

    async def _store_fact(self, scope_name: str, fact_id: str) -> tuple[ResolvedScope, FactFile]:
        """Validate the scope, resolve it, and read one note off-loop."""
        resolved = await self.resolved_scope(scope_name)
        ff = await asyncio.to_thread(read_fact, resolved.store_dir, fact_id)
        return resolved, ff


__all__ = ["KnowledgeService", "read_fact_file"]
