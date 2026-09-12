"""The single, global embedding configuration (redesign: embedding is no longer
per-resource).

One installation-wide ``EmbeddingConfig`` is shared by every knowledge scope. A
resource opts into vector retrieval by listing ``vector`` in its modes; whether
vector actually indexes depends on this global config being ``enabled`` and
complete. Changing the model/dimensions re-embeds every store (files are the
source of truth).

The config does not RESTATE a provider any more — it NAMES one. ``connection``
is the name of a configured LLM connection (a ``provider`` resource) and
``model`` one of the models that connection offers, exactly the "pick a
provider, then pick a model" shape the internal-engine setting has. The wire,
base URL and credential come from that connection at use time, so there is one
place to rotate a key and one place to correct an endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from coffer.domain.knowledge.embedder import EmbeddingConfig, EmbeddingProvider

#: The fixed primary key of the singleton ``embedding_config`` row.
SINGLETON_ID = 1

#: Connection wire → the embedding client that speaks it. ``openai`` and every
#: unclassified gateway (``unknown`` — an endpoint whose probe was inconclusive
#: is in practice OpenAI-compatible) use the OpenAI-compatible embeddings call;
#: ``ollama`` has its own keyless local endpoint. ``anthropic`` is ABSENT on
#: purpose: that wire exposes no embeddings API, so naming such a connection is
#: refused rather than silently producing a config that cannot embed.
#:
#: Held as plain protocol strings so this module does not import the provider
#: kind's config (which would drag the agent-projection vocabulary in with it).
EMBEDDING_PROTOCOLS: dict[str, EmbeddingProvider] = {
    "openai": "openai",
    "unknown": "openai",
    "ollama": "ollama",
}


def embedding_provider_for(protocol: str) -> EmbeddingProvider | None:
    """The embedding client for a connection's wire, or ``None`` when that wire
    serves no embeddings."""
    return EMBEDDING_PROTOCOLS.get(protocol)


@dataclass(frozen=True)
class EmbeddingEndpoint:
    """What a named connection contributes to an embedding call.

    ``offered_models`` is the connection's curated ``embedding``-modality ids,
    or ``None`` when it curates nothing at all — the "no restriction" answer,
    where Coffer knows where the calls go but not what that endpoint serves.
    """

    protocol: str
    base_url: str
    credential_ref: str | None
    offered_models: tuple[str, ...] | None


@dataclass
class GlobalEmbeddingConfig:
    """The one global embedding configuration.

    ``enabled`` is the master switch: when off (or when no connection/model is
    named), vector retrieval degrades to keyword everywhere, regardless of a
    resource's modes."""

    enabled: bool
    connection: str | None
    model: str | None
    dimensions: int
    default_chunk_size: int
    default_chunk_overlap: int
    updated_at: datetime

    def is_active(self) -> bool:
        """Whether vector indexing can actually run under this config."""
        return self.enabled and bool(self.connection) and bool(self.model)

    def to_embedding_config(self, endpoint: EmbeddingEndpoint | None) -> EmbeddingConfig | None:
        """Project onto the shared ``EmbeddingConfig`` VO using the named
        connection's endpoint, or ``None`` when vector is not active — the
        connection has been deleted, or its wire serves no embeddings. The
        caller then indexes keyword-only, which is the same degradation an
        unconfigured install already gets."""
        if not self.is_active() or endpoint is None:
            return None
        provider = embedding_provider_for(endpoint.protocol)
        if provider is None:
            return None
        return EmbeddingConfig(
            provider=provider,
            model=self.model or "",
            base_url=endpoint.base_url,
            credential_ref=endpoint.credential_ref,
            dimensions=self.dimensions,
        )
