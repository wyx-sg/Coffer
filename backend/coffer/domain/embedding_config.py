"""The single, global embedding configuration (redesign: embedding is no longer
per-resource).

One installation-wide ``EmbeddingConfig`` is shared by every knowledge base and
memory store. A resource opts into vector retrieval by listing ``vector`` in its
modes; whether vector actually indexes depends on this global config being
``enabled`` and complete. Changing the model/dimensions re-embeds every store
(files are the source of truth)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from coffer.domain.knowledge.embedder import EMBEDDING_PROVIDERS, EmbeddingConfig

#: The fixed primary key of the singleton ``embedding_config`` row.
SINGLETON_ID = 1


@dataclass
class GlobalEmbeddingConfig:
    """The one global embedding configuration.

    ``enabled`` is the master switch: when off (or when provider/model are not
    set), vector retrieval degrades to keyword everywhere, regardless of a
    resource's modes."""

    enabled: bool
    provider: str | None
    model: str | None
    base_url: str | None
    credential_ref: str | None
    dimensions: int
    updated_at: datetime

    def is_active(self) -> bool:
        """Whether vector indexing can actually run under this config."""
        return self.enabled and bool(self.provider) and bool(self.model)

    def to_embedding_config(self) -> EmbeddingConfig | None:
        """Project onto the shared ``EmbeddingConfig`` VO, or ``None`` when
        vector is not active (the caller then indexes keyword-only)."""
        if not self.is_active():
            return None
        provider = self.provider
        if provider not in EMBEDDING_PROVIDERS:
            return None
        return EmbeddingConfig(
            provider=provider,
            model=self.model or "",
            base_url=self.base_url,
            credential_ref=self.credential_ref,
            dimensions=self.dimensions,
        )
