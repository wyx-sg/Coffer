"""Retrieval helpers for ``MemoryService`` — lazy reindex-on-read recall.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These free functions own the reconcile→search→to-hits pipeline for a
single resolved store; ``MemoryService.recall`` / ``recall_in_store`` orchestrate
scope resolution and store-config lookup and delegate the per-store work here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service_helpers import to_memory_hits
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.knowledge.retrieval import MemoryHit, RetrievalMode, StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import ResolvedScope

#: ``store_name -> MemoryStoreConfig`` (validates the store exists).
ConfigFn = Callable[[str], Awaitable[MemoryStoreConfig]]
#: ``resolved -> store_name``.
StoreNameFn = Callable[[ResolvedScope], str]
#: ``store_name, project_id -> StoreRef``.
StoreRefFn = Callable[[str, str], StoreRef]

#: Requested recall span for the store-scoped REST face (mirrors the OpenAPI
#: ``RecallRequest.scope`` enum). ``project`` → the named store only; ``both`` /
#: ``global`` → also fold in the global store.
RecallScope = Literal["global", "project", "both"]


def _passage_mode(chosen: RetrievalMode) -> RetrievalMode:
    """Coerce a chosen store mode to one the passage engine can serve.

    Memory recall only ever serves passage modes — ``grep`` is a KB-only
    line-scanning mode that the passage engine cannot satisfy (it raises
    ``ValueError("grep is not a passage mode")``). The store config can still
    list ``grep`` (its default ``retrieval_modes`` is ``["grep", "keyword"]``),
    so we map it to ``keyword`` at the recall boundary rather than letting a dead
    mode reach ``retrieval.search`` (finding #1/#23)."""
    return "keyword" if chosen == "grep" else chosen


@dataclass(frozen=True)
class RecallDeps:
    """Collaborators the recall orchestrators need, bundled by the service so
    call sites stay short."""

    reconciler: MemoryReconciler
    retrieval: KnowledgeRetrieval
    get_config: ConfigFn
    store_name_for: StoreNameFn
    store_ref: StoreRefFn


async def recall_across(
    deps: RecallDeps,
    *,
    resolved_scopes: list[ResolvedScope],
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
) -> list[MemoryHit]:
    """Recall across several resolved scopes (project + global), merging hits."""
    hits: list[MemoryHit] = []
    for resolved in resolved_scopes:
        store_name = deps.store_name_for(resolved)
        config = await deps.get_config(store_name)
        hits.extend(
            await recall_one_store(
                reconciler=deps.reconciler,
                retrieval=deps.retrieval,
                store_ref=deps.store_ref(store_name, resolved.project_id),
                resolved=resolved,
                config=config,
                query=query,
                top_k=top_k,
                mode=mode,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


#: One extra store to fold into a store-scoped recall (e.g. the global store
#: when the REST request asks for ``scope=both``): ``(resolved, name, config)``.
ExtraStore = tuple[ResolvedScope, str, MemoryStoreConfig]


async def recall_single(
    deps: RecallDeps,
    *,
    resolved: ResolvedScope,
    store_name: str,
    config: MemoryStoreConfig,
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
    extra_stores: list[ExtraStore] | None = None,
) -> tuple[list[MemoryHit], RetrievalMode, bool]:
    """Recall within one store, optionally spanning ``extra_stores`` too.

    The primary store reports the effective mode + fallback (the REST face shows
    a single mode); ``extra_stores`` (e.g. the global store for ``scope=both``)
    contribute hits that are merged + re-ranked, so the store-scoped REST recall
    honours ``RecallRequest.scope`` (finding #5)."""
    hits, effective_mode, fallback = await recall_store_with_mode(
        reconciler=deps.reconciler,
        retrieval=deps.retrieval,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        resolved=resolved,
        config=config,
        query=query,
        top_k=top_k,
        mode=mode,
    )
    merged = list(hits)
    for extra_resolved, extra_name, extra_config in extra_stores or []:
        merged.extend(
            await recall_one_store(
                reconciler=deps.reconciler,
                retrieval=deps.retrieval,
                store_ref=deps.store_ref(extra_name, extra_resolved.project_id),
                resolved=extra_resolved,
                config=extra_config,
                query=query,
                top_k=top_k,
                mode=mode,
            )
        )
    merged.sort(key=lambda h: h.score, reverse=True)
    return merged[:top_k], effective_mode, fallback


#: ``store_name -> ResolvedScope`` (recovers a store's scope + on-disk dir).
ResolvedForFn = Callable[[str], Awaitable[ResolvedScope]]


async def recall_in_store_scoped(
    deps: RecallDeps,
    *,
    store_name: str,
    scope: RecallScope,
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
    get_config: ConfigFn,
    resolved_for: ResolvedForFn,
) -> tuple[list[MemoryHit], RetrievalMode, bool]:
    """Store-scoped REST recall that honours the request ``scope`` (finding #5).

    ``project`` (default) spans the named store only; ``both``/``global`` also
    fold in the global store (skipped when the named store IS global, to avoid
    double counting). The named store reports the effective mode + fallback."""
    config = await get_config(store_name)
    resolved = await resolved_for(store_name)
    extra: list[ExtraStore] | None = None
    if scope != "project" and store_name != GLOBAL_STORE_NAME:
        g_resolved = await resolved_for(GLOBAL_STORE_NAME)
        extra = [(g_resolved, GLOBAL_STORE_NAME, await get_config(GLOBAL_STORE_NAME))]
    return await recall_single(
        deps,
        resolved=resolved,
        store_name=store_name,
        config=config,
        query=query,
        top_k=top_k,
        mode=mode,
        extra_stores=extra,
    )


async def recall_one_store(
    *,
    reconciler: MemoryReconciler,
    retrieval: KnowledgeRetrieval,
    store_ref: StoreRef,
    resolved: ResolvedScope,
    config: MemoryStoreConfig,
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
) -> list[MemoryHit]:
    """Reconcile + search one resolved store, returning its hits.

    Used by the multi-scope ``recall`` path, which fans this out across the
    project + global stores and merges the results."""
    # Lazy reindex: pick up out-of-band deltas before searching.
    embedding = config.to_embedding_config() if config.vector_enabled else None
    await reconciler.reconcile(store=store_ref, embedding=embedding)
    chosen = mode or config.default_mode
    if chosen not in config.retrieval_modes:
        chosen = config.default_mode
    # Memory recall serves only passage modes; a configured/requested ``grep``
    # maps to ``keyword`` so a store whose ``default_mode`` is ``grep`` never
    # raises ``ValueError("grep is not a passage mode")`` (finding #1).
    result = await retrieval.search(
        store_ref,
        query,
        mode=_passage_mode(chosen),
        top_k=top_k,
        embedding=config.to_embedding_config(),
    )
    return to_memory_hits(result.passages, resolved)


async def recall_store_with_mode(
    *,
    reconciler: MemoryReconciler,
    retrieval: KnowledgeRetrieval,
    store_ref: StoreRef,
    resolved: ResolvedScope,
    config: MemoryStoreConfig,
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
) -> tuple[list[MemoryHit], RetrievalMode, bool]:
    """Reconcile + search one store, reporting the effective mode + fallback.

    Returns ``(hits, effective_mode, fallback)`` so the store-scoped REST face
    can report the mode actually used and whether a vector request degraded to
    keyword (no embedding configured) — never raising for the degrade path."""
    embedding = config.to_embedding_config() if config.vector_enabled else None
    await reconciler.reconcile(store=store_ref, embedding=embedding)
    chosen = mode or config.default_mode
    # A ``vector`` request the store cannot serve (vector not enabled / no
    # embedding configured) degrades to keyword and is flagged — never an
    # error (FR-008). Track the degrade explicitly so it is reported even
    # though the facade only sees the already-keyword mode.
    degraded = mode == "vector" and not config.vector_enabled
    if chosen not in config.retrieval_modes:
        chosen = config.default_mode
    result = await retrieval.search(
        store_ref,
        query,
        mode=_passage_mode(chosen),
        top_k=top_k,
        embedding=config.to_embedding_config(),
    )
    hits = to_memory_hits(result.passages, resolved)
    fallback = degraded or (result.fallback is not None)
    effective_mode: RetrievalMode = "keyword" if degraded else result.mode
    return hits, effective_mode, fallback
