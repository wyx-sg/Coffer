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

from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service_helpers import (
    grep_hits_to_memory_hits,
    passages_to_hits,
)
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.knowledge.document import KIND_MEMORY
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

#: Reciprocal-rank-fusion constant (the standard k=60 from the RRF paper).
_RRF_K = 60


def merge_ranked(groups: list[list[MemoryHit]], top_k: int) -> list[MemoryHit]:
    """Merge per-store hit lists by reciprocal rank fusion.

    Raw scores across stores are NOT comparable — flipped bm25 keyword scores
    are unbounded, vector scores are ≤1 and grep hits carry a flat score — so a
    raw-score sort lets one mode always dominate. RRF ranks by per-store
    position instead. Each hit keeps its original (per-store) score on the
    wire; only the merged ORDER comes from the fusion."""
    fused: dict[str, float] = {}
    by_id: dict[str, MemoryHit] = {}
    for group in groups:
        for rank, hit in enumerate(group):
            fused[hit.id] = fused.get(hit.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            by_id.setdefault(hit.id, hit)
    ordered = sorted(by_id.values(), key=lambda h: fused[h.id], reverse=True)
    return ordered[:top_k]


@dataclass(frozen=True)
class RecallDeps:
    """Collaborators the recall orchestrators need, bundled by the service so
    call sites stay short."""

    reconciler: MemoryReconciler
    retrieval: KnowledgeRetrieval
    documents: MemoryDocumentRepo
    get_config: ConfigFn
    store_name_for: StoreNameFn
    store_ref: StoreRefFn
    # Resolves the GLOBAL embedding config (embedding is no longer per-store).
    embedding_resolver: EmbeddingResolver = no_embedding


async def recall_spanning(
    deps: RecallDeps,
    *,
    resolver: object,
    cwd: str | None,
    query: str,
    scope: object | None = None,
    top_k: int = 5,
    mode: RetrievalMode | None = None,
) -> tuple[list[MemoryHit], bool]:
    """Lazy reindex-on-read recall, spanning project + global by default.

    Returns ``(hits, fallback)`` — ``fallback`` is True when any store degraded
    a vector request to keyword (no embedding configured)."""
    if scope is None:
        resolved_scopes = await resolver.resolve_recall_scopes(cwd=cwd)  # type: ignore[attr-defined]
    else:
        resolved_scopes = [await resolver.resolve(scope=scope, cwd=cwd)]  # type: ignore[attr-defined]
    return await recall_across(
        deps, resolved_scopes=resolved_scopes, query=query, top_k=top_k, mode=mode
    )


async def recall_across(
    deps: RecallDeps,
    *,
    resolved_scopes: list[ResolvedScope],
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
) -> tuple[list[MemoryHit], bool]:
    """Recall across several resolved scopes (project + global), merging hits.

    Returns ``(hits, fallback)`` — ``fallback`` is True when ANY store degraded
    a vector request to keyword, so the MCP tool can report it like the REST
    face does."""
    groups: list[list[MemoryHit]] = []
    fallback = False
    for resolved in resolved_scopes:
        store_name = deps.store_name_for(resolved)
        config = await deps.get_config(store_name)
        store_hits, _mode, store_fallback = await recall_store_with_mode(
            deps,
            store_ref=deps.store_ref(store_name, resolved.project_id),
            resolved=resolved,
            config=config,
            query=query,
            top_k=top_k,
            mode=mode,
        )
        groups.append(store_hits)
        fallback = fallback or store_fallback
    return merge_ranked(groups, top_k), fallback


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
        deps,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        resolved=resolved,
        config=config,
        query=query,
        top_k=top_k,
        mode=mode,
    )
    groups: list[list[MemoryHit]] = [list(hits)]
    for extra_resolved, extra_name, extra_config in extra_stores or []:
        extra_hits, _mode, extra_fallback = await recall_store_with_mode(
            deps,
            store_ref=deps.store_ref(extra_name, extra_resolved.project_id),
            resolved=extra_resolved,
            config=extra_config,
            query=query,
            top_k=top_k,
            mode=mode,
        )
        groups.append(extra_hits)
        fallback = fallback or extra_fallback
    return merge_ranked(groups, top_k), effective_mode, fallback


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

    ``project`` (default) spans the named store only; ``global`` queries the
    GLOBAL store only; ``both`` merges the named store with the global store
    (no double counting when the named store IS global). The primary store
    reports the effective mode + fallback."""
    if scope == "global":
        store_name = GLOBAL_STORE_NAME
    config = await get_config(store_name)
    resolved = await resolved_for(store_name)
    extra: list[ExtraStore] | None = None
    if scope == "both" and store_name != GLOBAL_STORE_NAME:
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


async def recall_store_with_mode(
    deps: RecallDeps,
    *,
    store_ref: StoreRef,
    resolved: ResolvedScope,
    config: MemoryStoreConfig,
    query: str,
    top_k: int,
    mode: RetrievalMode | None,
) -> tuple[list[MemoryHit], RetrievalMode, bool]:
    """Reconcile + search one store, reporting the effective mode + fallback.

    Returns ``(hits, effective_mode, fallback)`` so every face can report the
    mode actually used and whether a vector request degraded to keyword (no
    embedding configured) — never raising for the degrade path. ``grep`` is
    served for real: ripgrep over the store's fact files (FR-008) — essential
    for content FTS5 cannot tokenize (e.g. CJK)."""
    embedding = await deps.embedding_resolver() if config.vector_enabled else None
    await deps.reconciler.reconcile(store=store_ref, embedding=embedding)
    chosen = mode or config.default_mode
    # A ``vector`` request the store cannot serve (vector not enabled / no
    # embedding configured) degrades to keyword and is flagged — never an
    # error (FR-008). Track the degrade explicitly so it is reported even
    # though the facade only sees the already-keyword mode.
    degraded = mode == "vector" and not config.vector_enabled
    if chosen not in config.retrieval_modes:
        chosen = config.default_mode
    if degraded and chosen == "vector":
        chosen = "keyword"

    if chosen == "grep":
        # Line budget wider than top_k: dedupe (many matching lines in one
        # fact → one hit) happens BEFORE the cut, so a verbose fact can't
        # starve the other matching facts.
        grep_result = await deps.retrieval.grep(store_ref, query, max_matches=max(top_k * 10, 100))
        grep_hits = grep_hits_to_memory_hits(grep_result.hits, resolved)[:top_k]
        return grep_hits, "grep", False

    result = await deps.retrieval.search(
        store_ref,
        query,
        mode=chosen,
        top_k=top_k,
        embedding=embedding,
    )

    async def _get_doc(fact_id: str):  # type: ignore[no-untyped-def]
        return await deps.documents.get_document(KIND_MEMORY, store_ref.resource_name, fact_id)

    hits = await passages_to_hits(result.passages, resolved, _get_doc)
    fallback = degraded or (result.fallback is not None)
    effective_mode: RetrievalMode = "keyword" if degraded else result.mode
    return hits, effective_mode, fallback
