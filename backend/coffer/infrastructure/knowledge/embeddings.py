"""Embedding clients behind the ``Embedder`` port.

DevPilot-style: one ``AsyncOpenAI`` client whose ``base_url`` is swapped per
provider (PROVIDER_BASE_URLS), plus an in-process ``local`` provider via
fastembed. The ONLY importer of ``openai`` / ``fastembed`` — both lazy so the
daemon starts without them; a missing lib raises ``EngineUnavailable`` and the
caller degrades vector→keyword.

Credentials are resolved via a keychain adapter (a callable ``ref -> secret``)
so no plaintext ever lives in config or here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import EmbeddingConfig

#: provider id → default OpenAI-compatible base URL. ``None`` means "use the SDK
#: default" (openai) and ``local`` is handled out of band (fastembed).
PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "voyage": "https://api.voyageai.com/v1",
    "jina": "https://api.jina.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "azure": None,  # base_url must be supplied explicitly for azure
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}

#: A ``credential_ref -> secret | None`` resolver (the keychain adapter's get).
CredentialResolver = Callable[[str], str | None]


def _validate_widths(vectors: list[list[float]], expected: int) -> list[list[float]]:
    """Ensure every embedding matches the configured width.

    A model/config width mismatch otherwise surfaces only as a raw sqlite-vec
    constraint error from inside ``to_thread`` at insert time; catch it here as
    a clear ``EngineUnavailable`` so the caller degrades vector→keyword.
    """
    for vec in vectors:
        if len(vec) != expected:
            raise EngineUnavailable(
                "embedding",
                f"model returned width {len(vec)} but config declares {expected}; "
                "fix the store's 'dimensions' to match the model",
            )
    return vectors


class OpenAICompatibleEmbedder:
    """OpenAI-compatible embedding client with a swappable ``base_url``."""

    def __init__(
        self,
        config: EmbeddingConfig,
        *,
        resolve_credential: CredentialResolver | None = None,
    ) -> None:
        self._config = config
        self._resolve = resolve_credential
        self._client: Any | None = None

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    def _api_key(self) -> str:
        if self._config.credential_ref and self._resolve is not None:
            secret = self._resolve(self._config.credential_ref)
            if secret:
                return secret
        # Keyless endpoints (ollama/lmstudio) still want a non-empty token.
        return "not-needed"

    def _base_url(self) -> str | None:
        if self._config.base_url:
            return self._config.base_url
        return PROVIDER_BASE_URLS.get(self._config.provider)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise EngineUnavailable(
                "openai", "install the 'openai' package for cloud embeddings"
            ) from exc
        self._client = AsyncOpenAI(api_key=self._api_key(), base_url=self._base_url())
        return self._client

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        try:
            resp = await client.embeddings.create(model=self._config.model, input=list(texts))
        except Exception as exc:
            raise EngineUnavailable("embedding", f"provider call failed: {exc}") from exc
        # The OpenAI contract does NOT guarantee response order matches input
        # order; each item carries its ``index``. Sort by it to keep embeddings
        # aligned with their source texts.
        ordered = sorted(resp.data, key=lambda d: d.index)
        return _validate_widths([list(item.embedding) for item in ordered], self.dimensions)


class LocalEmbedder:
    """In-process embeddings via fastembed (no network)."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model: Any | None = None

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover
            raise EngineUnavailable(
                "fastembed", "install the 'fastembed' extra for local embeddings"
            ) from exc
        try:
            self._model = TextEmbedding(model_name=self._config.model)
        except Exception as exc:
            raise EngineUnavailable("fastembed", f"model load failed: {exc}") from exc
        return self._model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        import asyncio

        model = self._ensure_model()

        def _run() -> list[list[float]]:
            return [list(vec) for vec in model.embed(list(texts))]

        return _validate_widths(await asyncio.to_thread(_run), self.dimensions)


def make_embedder(
    config: EmbeddingConfig,
    *,
    resolve_credential: CredentialResolver | None = None,
) -> OpenAICompatibleEmbedder | LocalEmbedder:
    """Build the right ``Embedder`` for the configured provider."""
    if config.provider == "local":
        return LocalEmbedder(config)
    return OpenAICompatibleEmbedder(config, resolve_credential=resolve_credential)
