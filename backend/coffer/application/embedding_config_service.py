"""Global embedding configuration service.

One installation-wide embedding config shared by every knowledge scope
(redesign: embedding is no longer per-resource). The reindex/substrate reads
``resolve()`` to build the embedder and decide the vec table width; the Settings
surface calls ``update()``.

The config NAMES a connection rather than restating one, so this service holds
the only two things that cannot live in the domain: the lookup of that
connection (a port, wired at the composition root — the provider kind never
enters here) and the rules for refusing a connection that cannot embed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.embedding_config import (
    EmbeddingEndpoint,
    GlobalEmbeddingConfig,
    embedding_provider_for,
)
from coffer.domain.errors import ConfigValidationError
from coffer.domain.knowledge.embedder import EmbeddingConfig

#: Default vector width when the operator has never configured embedding.
DEFAULT_DIMENSIONS = 768


class EmbeddingConnectionPort(Protocol):
    """The LLM connections, narrowed to the one question this service asks of
    them: what does the connection called ``name`` contribute to an embedding
    call, and which embedding models does it offer? ``None`` when no connection
    goes by that name."""

    async def endpoint(self, name: str) -> EmbeddingEndpoint | None: ...


class EmbeddingConfigRepo(Protocol):
    async def get(self) -> GlobalEmbeddingConfig | None: ...
    async def set(
        self,
        *,
        enabled: bool,
        connection: str | None,
        model: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
    ) -> GlobalEmbeddingConfig: ...


def _default() -> GlobalEmbeddingConfig:
    return GlobalEmbeddingConfig(
        enabled=False,
        connection=None,
        model=None,
        dimensions=DEFAULT_DIMENSIONS,
        default_chunk_size=512,
        default_chunk_overlap=64,
        updated_at=datetime.now(tz=UTC),
    )


class EmbeddingConfigService:
    """Reads/writes the singleton global embedding config."""

    def __init__(
        self,
        repo: EmbeddingConfigRepo,
        audit: AuditService,
        connections: EmbeddingConnectionPort,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._connections = connections

    async def get(self) -> GlobalEmbeddingConfig:
        """The current config, or a disabled default when never configured."""
        return await self._repo.get() or _default()

    async def resolve(self) -> EmbeddingConfig | None:
        """The embedder settings to index/recall with, or ``None`` when vector is
        off — the switch is off, no connection is named, the named connection is
        gone, or its wire serves no embeddings. Every ``None`` degrades to
        keyword/grep; none of them is an error at read time."""
        cfg = await self.get()
        if not cfg.is_active():
            return None
        assert cfg.connection is not None  # is_active() guarantees it
        return cfg.to_embedding_config(await self._connections.endpoint(cfg.connection))

    async def endpoint_for(self, connection: str, model: str) -> EmbeddingEndpoint:
        """The endpoint to probe ``model`` on, or a ``ConfigValidationError``
        naming exactly what is wrong. Shared by ``update()`` and the test route,
        so "I can save this" and "I can test this" answer the same way."""
        return await self._validated(connection, model)

    async def update(
        self,
        *,
        enabled: bool,
        connection: str | None,
        model: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
        actor: str,
    ) -> GlobalEmbeddingConfig:
        """Persist the global config. Enabling vector requires a connection and a
        model so the substrate can actually build an embedder; naming a
        connection that cannot serve the model is refused here rather than
        discovered later by a silently keyword-only index."""
        connection = connection.strip() if connection and connection.strip() else None
        model = model.strip() if model and model.strip() else None
        if enabled and not (connection and model):
            raise ConfigValidationError("connection and model are required to enable embedding")
        if not 1 <= dimensions <= 8192:
            raise ConfigValidationError(f"dimensions must be in 1..8192, got {dimensions}")
        if not 64 <= default_chunk_size <= 2048:
            raise ConfigValidationError(f"chunk size must be in 64..2048, got {default_chunk_size}")
        if default_chunk_overlap < 0 or default_chunk_overlap > default_chunk_size // 2:
            raise ConfigValidationError("chunk overlap must be in 0..chunk_size/2")
        if connection:
            await self._validated(connection, model)
        saved = await self._repo.set(
            enabled=enabled,
            connection=connection,
            model=model,
            dimensions=dimensions,
            default_chunk_size=default_chunk_size,
            default_chunk_overlap=default_chunk_overlap,
        )
        await self._audit.record(
            AuditEventType.EMBEDDING_CONFIG_UPDATED.value,
            actor=actor,
            details={
                "enabled": saved.enabled,
                "connection": saved.connection,
                "model": saved.model,
                "dimensions": saved.dimensions,
                "default_chunk_size": saved.default_chunk_size,
                "default_chunk_overlap": saved.default_chunk_overlap,
            },
        )
        return saved

    # --- internals -----------------------------------------------------------

    async def _validated(self, connection: str, model: str | None) -> EmbeddingEndpoint:
        """Refuse, with a message the UI can show verbatim, a connection that
        cannot serve this embedding model."""
        endpoint = await self._connections.endpoint(connection)
        if endpoint is None:
            raise ConfigValidationError(f"no connection named {connection!r}")
        if embedding_provider_for(endpoint.protocol) is None:
            raise ConfigValidationError(
                f"connection {connection!r} speaks {endpoint.protocol}, which serves no "
                "embedding API; pick an openai-compatible or ollama connection"
            )
        offered = endpoint.offered_models
        if offered is None:
            # The connection curates nothing: "no restriction". Coffer knows
            # where the calls go, not what the endpoint serves, so the typed
            # model id is taken at its word (the same rule a chat picker uses).
            return endpoint
        if not offered:
            raise ConfigValidationError(
                f"connection {connection!r} offers no embedding model; add one to its "
                "model list with modality 'embedding'"
            )
        if model is not None and model not in offered:
            raise ConfigValidationError(
                f"connection {connection!r} does not offer embedding model {model!r}; "
                f"it offers {', '.join(offered)}"
            )
        return endpoint
