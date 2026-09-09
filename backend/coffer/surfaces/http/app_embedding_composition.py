"""Embedding-resolver builders for the app lifespan.

Split out of :mod:`coffer.surfaces.http.app` for the file-size budget. Builds the
two embedding resolvers the lifespan wires into KB/memory and the gateway's
semantic search_tools (ADR-024).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.knowledge.embeddings import make_embedder


def build_config_services(app: Any, sm: Any, audit: Any, credential_store: Any) -> tuple[Any, Any]:
    """Build the two engine-config singletons and register their synced state
    area (spec 010 slice 7) before start_sync snapshots the provider list."""
    from coffer.application.engine_settings_sync import EngineSettingsSyncState
    from coffer.application.internal_engine_config_service import InternalEngineConfigService
    from coffer.infrastructure.persistence.repos import (
        SqlAlchemyEmbeddingConfigRepo,
        SqlAlchemyInternalEngineConfigRepo,
    )

    embedding_repo = SqlAlchemyEmbeddingConfigRepo(sm)
    embedding_svc = EmbeddingConfigService(
        repo=embedding_repo, audit=audit, credentials=credential_store
    )
    internal_repo = SqlAlchemyInternalEngineConfigRepo(sm)
    internal_svc = InternalEngineConfigService(repo=internal_repo, audit=audit)
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(
        EngineSettingsSyncState(
            embedding_svc,
            internal_svc,
            embedding_repo=embedding_repo,
            internal_repo=internal_repo,
        )
    )
    return embedding_svc, internal_svc


def build_embedding_resolvers(
    embedding_config_svc: EmbeddingConfigService,
    credential_store: Any,
) -> tuple[Callable[[], Awaitable[object]], Callable[[], Awaitable[object | None]]]:
    """Return ``(resolve_embedding, tool_search_embedder)``.

    Embedding is global: KB + memory resolve the current config at index/recall
    time so a Settings change applies without a daemon restart. The tool-search
    embedder reuses the KB embedder (or None when embeddings are off/unavailable
    → gateway BM25 fallback), cached per config to reuse the underlying client.
    """

    async def _resolve_embedding() -> object:
        return (await embedding_config_svc.get()).to_embedding_config()

    _ts_embedder_cache: dict[tuple[object, ...], object] = {}

    async def _tool_search_embedder() -> object | None:
        embedding = cast(EmbeddingConfig | None, await _resolve_embedding())
        if embedding is None:
            return None
        key = (
            embedding.provider,
            embedding.model,
            embedding.base_url,
            embedding.credential_ref,
            embedding.dimensions,
        )
        embedder = _ts_embedder_cache.get(key)
        if embedder is None:
            try:
                embedder = make_embedder(embedding, resolve_credential=credential_store.get)
            except Exception:
                return None
            _ts_embedder_cache[key] = embedder
        return embedder

    return _resolve_embedding, _tool_search_embedder
