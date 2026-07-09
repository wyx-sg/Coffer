"""Engine settings as a synced state area (spec 010 slice 7).

The embedding configuration and the internal-engine model choice are
installation-wide singletons that should match across machines: vector
indexes rebuild per machine and only converge when both embed with the same
model. Secrets stay refs (the ciphertext syncs separately).
"""

from __future__ import annotations

from typing import Any, Protocol

from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.internal_engine_config_service import InternalEngineConfigService

AREA = "settings"


class _SingletonRow(Protocol):
    async def get(self) -> object | None: ...


class EngineSettingsSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(
        self,
        embedding: EmbeddingConfigService,
        internal_engine: InternalEngineConfigService,
        *,
        embedding_repo: _SingletonRow,
        internal_repo: _SingletonRow,
    ) -> None:
        self._embedding = embedding
        self._internal = internal_engine
        self._embedding_repo = embedding_repo
        self._internal_repo = internal_repo

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        # Own (and publish) only singletons this machine has actually
        # persisted: a fresh machine exporting synthesized defaults would
        # same-path conflict with the fleet's values on its very first
        # unrelated-histories merge. Until the row exists locally, the doc is
        # preserved verbatim and applied at import like any foreign state.
        docs: list[tuple[str, dict[str, object]]] = []
        owned: list[str] = []
        if await self._embedding_repo.get() is not None:
            emb = await self._embedding.get()
            owned.append("embedding")
            docs.append(
                (
                    "embedding",
                    {
                        "enabled": emb.enabled,
                        "provider": emb.provider,
                        "model": emb.model,
                        "base_url": emb.base_url,
                        "credential_ref": emb.credential_ref,
                        "dimensions": emb.dimensions,
                        "default_chunk_size": emb.default_chunk_size,
                        "default_chunk_overlap": emb.default_chunk_overlap,
                    },
                )
            )
        if await self._internal_repo.get() is not None:
            internal = await self._internal.get()
            owned.append("internal-engine")
            docs.append(("internal-engine", {"model": internal.model}))
        return docs, owned

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[str]:
        errors: list[str] = []
        for path, doc in docs:
            try:
                if path == "embedding":
                    await self._import_embedding(doc)
                elif path == "internal-engine":
                    current = await self._internal.get()
                    raw = doc.get("model")
                    model = str(raw) if raw else None
                    if model != current.model:
                        await self._internal.update(model=model, actor="sync")
            except Exception as e:
                errors.append(f"settings/{path}: {e}")
        return errors

    async def _import_embedding(self, doc: dict[str, Any]) -> None:
        current = await self._embedding.get()

        def _int(key: str, fallback: int) -> int:
            raw = doc.get(key)
            return int(raw) if isinstance(raw, int) else fallback

        enabled = bool(doc.get("enabled", False))
        provider = str(doc["provider"]) if doc.get("provider") else None
        model = str(doc["model"]) if doc.get("model") else None
        base_url = str(doc["base_url"]) if doc.get("base_url") else None
        credential_ref = str(doc["credential_ref"]) if doc.get("credential_ref") else None
        dimensions = _int("dimensions", current.dimensions)
        chunk_size = _int("default_chunk_size", current.default_chunk_size)
        chunk_overlap = _int("default_chunk_overlap", current.default_chunk_overlap)
        if (
            current.enabled == enabled
            and current.provider == provider
            and current.model == model
            and current.base_url == base_url
            and current.credential_ref == credential_ref
            and current.dimensions == dimensions
            and current.default_chunk_size == chunk_size
            and current.default_chunk_overlap == chunk_overlap
        ):
            return
        await self._embedding.update(
            enabled=enabled,
            provider=provider,
            model=model,
            base_url=base_url,
            credential_ref=credential_ref,
            dimensions=dimensions,
            default_chunk_size=chunk_size,
            default_chunk_overlap=chunk_overlap,
            actor="sync",
        )
