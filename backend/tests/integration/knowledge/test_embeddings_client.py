"""Integration: the OpenAI-compatible embedding client (SDK mocked)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

import pytest

from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.knowledge.embeddings import (
    PROVIDER_BASE_URLS,
    OpenAICompatibleEmbedder,
    make_embedder,
)


class _FakeEmbeddingsResp:
    def __init__(self, items: Sequence[tuple[int, Sequence[float]]]) -> None:
        # Each item carries its ``index`` (per the OpenAI contract) so the
        # embedder can re-align embeddings to input order regardless of the
        # order ``data`` arrives in.
        self.data = [type("E", (), {"index": i, "embedding": list(v)})() for i, v in items]


class _FakeAsyncOpenAI:
    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        _FakeAsyncOpenAI.last_kwargs = kwargs

        async def _create(*, model: str, input: list[str]) -> _FakeEmbeddingsResp:
            return _FakeEmbeddingsResp([(i, [float(len(t))] * 3) for i, t in enumerate(input)])

        self.embeddings = type("Emb", (), {"create": staticmethod(_create)})()


def _cfg(provider: str = "openai", base_url: str | None = None) -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=provider,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        base_url=base_url,
        credential_ref="my-ref",
        dimensions=3,
    )


@pytest.mark.asyncio
async def test_embed_uses_resolved_credential_and_base_url(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    resolved: list[str] = []

    def resolver(ref: str) -> str | None:
        resolved.append(ref)
        return "sk-secret"

    emb = OpenAICompatibleEmbedder(_cfg("openrouter"), resolve_credential=resolver)
    out = await emb.embed(["hello", "world!!"])
    assert out == [[5.0, 5.0, 5.0], [7.0, 7.0, 7.0]]
    assert resolved == ["my-ref"]
    assert _FakeAsyncOpenAI.last_kwargs["api_key"] == "sk-secret"
    assert _FakeAsyncOpenAI.last_kwargs["base_url"] == PROVIDER_BASE_URLS["openrouter"]


@pytest.mark.asyncio
async def test_embed_realigns_shuffled_response_by_index(monkeypatch) -> None:
    """``resp.data`` may arrive out of input order; the embedder must re-align by
    each item's ``index`` so embeddings stay matched to their source texts."""
    import openai

    class _ShuffledOpenAI:
        def __init__(self, **_kw: Any) -> None:
            async def _create(*, model: str, input: list[str]) -> _FakeEmbeddingsResp:
                # Distinct vector per index, returned in REVERSE order.
                items = [(i, [float(i)] * 3) for i in range(len(input))]
                return _FakeEmbeddingsResp(list(reversed(items)))

            self.embeddings = type("E", (), {"create": staticmethod(_create)})()

    monkeypatch.setattr(openai, "AsyncOpenAI", _ShuffledOpenAI)
    emb = OpenAICompatibleEmbedder(_cfg(), resolve_credential=lambda _r: "k")
    out = await emb.embed(["a", "b", "c"])
    # Output must follow INPUT order (0,1,2), not the shuffled response order.
    assert out == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]


@pytest.mark.asyncio
async def test_embed_width_mismatch_raises_engine_unavailable(monkeypatch) -> None:
    """A model returning the wrong width is caught as a clear config error rather
    than surfacing as a raw sqlite-vec constraint error at insert time."""
    import openai

    class _WrongWidthOpenAI:
        def __init__(self, **_kw: Any) -> None:
            async def _create(*, model: str, input: list[str]) -> _FakeEmbeddingsResp:
                # config declares dimensions=3; return width 5.
                return _FakeEmbeddingsResp([(i, [0.0] * 5) for i, _ in enumerate(input)])

            self.embeddings = type("E", (), {"create": staticmethod(_create)})()

    monkeypatch.setattr(openai, "AsyncOpenAI", _WrongWidthOpenAI)
    emb = OpenAICompatibleEmbedder(_cfg(), resolve_credential=lambda _r: "k")
    with pytest.raises(EngineUnavailable):
        await emb.embed(["x"])


def test_dashscope_base_url_is_correct() -> None:
    """Regression: the dashscope host was a typo (aliyahd → aliyuncs)."""
    assert PROVIDER_BASE_URLS["dashscope"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


@pytest.mark.asyncio
async def test_embed_empty_short_circuits(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    emb = OpenAICompatibleEmbedder(_cfg(), resolve_credential=lambda _r: "k")
    assert await emb.embed([]) == []


@pytest.mark.asyncio
async def test_provider_failure_raises_engine_unavailable(monkeypatch) -> None:
    import openai

    class _Boom:
        def __init__(self, **_kw: Any) -> None:
            async def _create(**_k: Any) -> None:
                raise RuntimeError("network down")

            self.embeddings = type("E", (), {"create": staticmethod(_create)})()

    monkeypatch.setattr(openai, "AsyncOpenAI", _Boom)
    emb = OpenAICompatibleEmbedder(_cfg(), resolve_credential=lambda _r: "k")
    with pytest.raises(EngineUnavailable):
        await emb.embed(["x"])


def test_make_embedder_local_uses_fastembed_path() -> None:
    from coffer.infrastructure.knowledge.embeddings import LocalEmbedder

    cfg = EmbeddingConfig(provider="local", model="bge-m3", dimensions=1024)
    assert isinstance(make_embedder(cfg), LocalEmbedder)


def test_dimensions_exposed() -> None:
    emb = make_embedder(_cfg())
    assert emb.dimensions == 3
