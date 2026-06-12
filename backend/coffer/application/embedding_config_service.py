"""Global embedding configuration service.

One installation-wide embedding config shared by every knowledge base and memory
store (redesign: embedding is no longer per-resource). The reindex/substrate
reads ``get()`` to build the embedder and decide the vec table width; the
Settings surface calls ``update()``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.embedding_config import GlobalEmbeddingConfig
from coffer.domain.errors import ConfigValidationError

#: Default vector width when the operator has never configured embedding.
DEFAULT_DIMENSIONS = 768


class EmbeddingConfigRepo(Protocol):
    async def get(self) -> GlobalEmbeddingConfig | None: ...
    async def set(
        self,
        *,
        enabled: bool,
        provider: str | None,
        model: str | None,
        base_url: str | None,
        credential_ref: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
    ) -> GlobalEmbeddingConfig: ...


def _default() -> GlobalEmbeddingConfig:
    return GlobalEmbeddingConfig(
        enabled=False,
        provider=None,
        model=None,
        base_url=None,
        credential_ref=None,
        dimensions=DEFAULT_DIMENSIONS,
        default_chunk_size=512,
        default_chunk_overlap=64,
        updated_at=datetime.now(tz=UTC),
    )


class EmbeddingConfigService:
    """Reads/writes the singleton global embedding config."""

    def __init__(self, repo: EmbeddingConfigRepo, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def get(self) -> GlobalEmbeddingConfig:
        """The current config, or a disabled default when never configured."""
        return await self._repo.get() or _default()

    async def update(
        self,
        *,
        enabled: bool,
        provider: str | None,
        model: str | None,
        base_url: str | None,
        credential_ref: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
        actor: str,
    ) -> GlobalEmbeddingConfig:
        """Persist the global config. Enabling vector requires provider+model so
        the substrate can actually build an embedder."""
        if enabled and not (provider and model):
            raise ConfigValidationError("provider and model are required to enable embedding")
        if not 1 <= dimensions <= 8192:
            raise ConfigValidationError(f"dimensions must be in 1..8192, got {dimensions}")
        if not 64 <= default_chunk_size <= 2048:
            raise ConfigValidationError(f"chunk size must be in 64..2048, got {default_chunk_size}")
        if default_chunk_overlap < 0 or default_chunk_overlap > default_chunk_size // 2:
            raise ConfigValidationError("chunk overlap must be in 0..chunk_size/2")
        saved = await self._repo.set(
            enabled=enabled,
            provider=provider or None,
            model=model or None,
            base_url=base_url or None,
            credential_ref=credential_ref or None,
            dimensions=dimensions,
            default_chunk_size=default_chunk_size,
            default_chunk_overlap=default_chunk_overlap,
        )
        await self._audit.record(
            AuditEventType.EMBEDDING_CONFIG_UPDATED.value,
            actor=actor,
            details={
                "enabled": saved.enabled,
                "provider": saved.provider,
                "model": saved.model,
                "dimensions": saved.dimensions,
                "default_chunk_size": saved.default_chunk_size,
                "default_chunk_overlap": saved.default_chunk_overlap,
            },
        )
        return saved
