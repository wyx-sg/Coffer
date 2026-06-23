"""Global embedding configuration service.

One installation-wide embedding config shared by every knowledge base and memory
store (redesign: embedding is no longer per-resource). The reindex/substrate
reads ``get()`` to build the embedder and decide the vec table width; the
Settings surface calls ``update()``."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.embedding_config import GlobalEmbeddingConfig
from coffer.domain.errors import ConfigValidationError

#: Default vector width when the operator has never configured embedding.
DEFAULT_DIMENSIONS = 768

#: Fixed vault ref the embedding config stores its API key under. There is only
#: one global embedding model, so a single well-known ref suffices (mirrors the
#: provider service's ``provider/<name>/key`` convention).
EMBEDDING_CREDENTIAL_REF = "embedding/key"


class _CredentialStore(Protocol):
    """The synchronous credential vault (short-lived SQLite connections); we run
    it off the event loop via ``asyncio.to_thread`` like the provider service."""

    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


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

    def __init__(
        self,
        repo: EmbeddingConfigRepo,
        audit: AuditService,
        credentials: _CredentialStore,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._credentials = credentials

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
        secret_value: str | None = None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
        actor: str,
    ) -> GlobalEmbeddingConfig:
        """Persist the global config. Enabling vector requires provider+model so
        the substrate can actually build an embedder.

        A raw ``secret_value`` (the API key the user typed) is stored into the
        credential vault under :data:`EMBEDDING_CREDENTIAL_REF` and reused as the
        ``credential_ref``; it takes precedence over an explicit ``credential_ref``.
        """
        if enabled and not (provider and model):
            raise ConfigValidationError("provider and model are required to enable embedding")
        if not 1 <= dimensions <= 8192:
            raise ConfigValidationError(f"dimensions must be in 1..8192, got {dimensions}")
        if not 64 <= default_chunk_size <= 2048:
            raise ConfigValidationError(f"chunk size must be in 64..2048, got {default_chunk_size}")
        if default_chunk_overlap < 0 or default_chunk_overlap > default_chunk_size // 2:
            raise ConfigValidationError("chunk overlap must be in 0..chunk_size/2")
        if secret_value is not None:
            await asyncio.to_thread(self._credentials.set, EMBEDDING_CREDENTIAL_REF, secret_value)
            credential_ref = EMBEDDING_CREDENTIAL_REF
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
