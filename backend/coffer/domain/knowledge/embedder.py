"""``EmbeddingConfig`` value object + the ``Embedder`` port.

DevPilot-style OpenAI-compatible provider abstraction: one client with a
swappable ``base_url`` per provider, plus an in-process ``local`` option.
Concrete clients live in ``infrastructure/knowledge/embeddings.py`` (the only
importer of ``openai`` / ``fastembed``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

#: Provider ids accepted in config. ``local`` runs fastembed in-process; every
#: other id maps to an OpenAI-compatible HTTP endpoint (see PROVIDER_BASE_URLS
#: in the infrastructure client).
EmbeddingProvider = Literal[
    "openai",
    "openrouter",
    "voyage",
    "jina",
    "gemini",
    "azure",
    "dashscope",
    "ollama",
    "lmstudio",
    "local",
]
EMBEDDING_PROVIDERS: tuple[EmbeddingProvider, ...] = (
    "openai",
    "openrouter",
    "voyage",
    "jina",
    "gemini",
    "azure",
    "dashscope",
    "ollama",
    "lmstudio",
    "local",
)


class EmbeddingConfig(BaseModel):
    """Per-store embedding settings. Mutable: changing ``model``/``dimensions``
    re-embeds the corpus (files are the source of truth)."""

    provider: EmbeddingProvider
    model: str = Field(min_length=1)
    base_url: str | None = None
    credential_ref: str | None = None
    dimensions: int = Field(ge=1, le=8192)

    def model_post_init(self, __context: object) -> None:
        # The OpenAI-compatible (non-local, non-keyless) cloud providers need a
        # credential ref; ``local``/``ollama``/``lmstudio`` are keyless.
        keyless = {"local", "ollama", "lmstudio"}
        if self.provider not in keyless and not self.credential_ref:
            # Not fatal at config time — the client may fall back to the LLM
            # credential ref — but record intent. We do not raise here so a KB
            # can be created before its key is stored.
            pass


@runtime_checkable
class Embedder(Protocol):
    """Embeds text into fixed-width vectors."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text. Raises ``EngineUnavailable`` if
        the provider library/endpoint is unavailable."""
        ...

    @property
    def dimensions(self) -> int:
        """Vector width this embedder produces."""
        ...
