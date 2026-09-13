"""Remote embeddings (spec knowledge FR-026/FR-027).

``httpx.MockTransport`` makes real request/response round trips without a
socket, which the unit tier bans (see ``scripts/check_unit_purity.py``) — that
is why this test lives in the integration tier rather than alongside
``tests/unit/llm/test_transcription.py``.

The gate that matters most: any malformed or short response degrades to an
empty tuple (never a partial index, never a raised exception), because the
caller's contract is "() means fall back to literal search", not "figure out
which of these vectors are trustworthy".
"""

from __future__ import annotations

import json

import httpx
import pytest

from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.llm.embeddings import RemoteEmbedder, remote_embedder


def _conn(protocol: Protocol = Protocol.OPENAI, ref: str | None = "provider/x/key"):
    return ResolvedConnection(
        config=ProviderConfig(
            protocol=protocol, base_url="https://api.example/v1", credential_ref=ref
        ),
        model="text-embedding-3-small",
    )


def _ollama_conn():
    return ResolvedConnection(
        config=ProviderConfig(
            protocol=Protocol.OLLAMA, base_url="http://localhost:11434/v1", credential_ref=None
        ),
        model="nomic-embed-text",
    )


def _vector(seed: float, dims: int = 3) -> list[float]:
    return [seed + i for i in range(dims)]


# ``RemoteEmbedder`` builds its own ``httpx.AsyncClient`` per call (mirroring
# ``RemoteTranscriber``), so tests monkeypatch the transport ``httpx.AsyncClient``
# is constructed with rather than reaching into private state.
def _patched(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    import coffer.infrastructure.llm.embeddings as mod

    real_client = mod.httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = handler
        return real_client(*args, **kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _client)


def _handler_ok(dims: int = 3):
    def _h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        texts = body["input"]
        data = [{"index": i, "embedding": _vector(float(i), dims)} for i in range(len(texts))]
        return httpx.Response(200, json={"data": data})

    return _h


async def test_happy_path_several_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    _patched(monkeypatch, httpx.MockTransport(_handler_ok()))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    result = await embedder.embed(["alpha", "beta", "gamma"])
    assert result == ((0.0, 1.0, 2.0), (1.0, 2.0, 3.0), (2.0, 3.0, 4.0))


async def test_empty_input_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _h(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": []})

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    assert await embedder.embed([]) == ()
    assert called is False


async def test_non_2xx_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream exploded")

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    assert await embedder.embed(["x"]) == ()


async def test_malformed_json_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json{{{")

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    assert await embedder.embed(["x"]) == ()


async def test_vector_count_mismatch_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    def _h(request: httpx.Request) -> httpx.Response:
        # Two texts requested, only one vector returned.
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    assert await embedder.embed(["x", "y"]) == ()


async def test_missing_embedding_field_returns_empty_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0}]})

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None
    assert await embedder.embed(["x"]) == ()


async def test_batching_across_the_cap_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from coffer.infrastructure.llm import embeddings as mod

    batch_calls: list[int] = []

    def _h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        texts = body["input"]
        batch_calls.append(len(texts))
        data = [{"index": i, "embedding": _vector(float(i), 1)} for i, t in enumerate(texts)]
        return httpx.Response(200, json={"data": data})

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None

    total = mod._BATCH_SIZE + 5
    texts = [f"text-{i}" for i in range(total)]
    result = await embedder.embed(texts)

    assert len(result) == total
    # each vector is [float(local_index)] within its batch — reassembling the
    # local indices back to back must reproduce 0..batch_size-1 twice (once
    # per batch), proving order survived across the request boundary.
    assert [v[0] for v in result] == [float(i % mod._BATCH_SIZE) for i in range(total)]
    assert len(batch_calls) == 2
    assert batch_calls == [mod._BATCH_SIZE, 5]


async def test_a_failed_batch_fails_the_whole_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial index is worse than none: if the second batch fails, the
    vectors already fetched from the first batch must NOT be returned."""
    from coffer.infrastructure.llm import embeddings as mod

    call_count = 0

    def _h(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            body = json.loads(request.content)
            texts = body["input"]
            data = [{"index": i, "embedding": [0.0]} for i in range(len(texts))]
            return httpx.Response(200, json={"data": data})
        return httpx.Response(500, text="boom")

    _patched(monkeypatch, httpx.MockTransport(_h))
    embedder = remote_embedder(_conn(), "sk-secret")
    assert embedder is not None

    total = mod._BATCH_SIZE + 1
    texts = [f"text-{i}" for i in range(total)]
    assert await embedder.embed(texts) == ()
    assert call_count == 2


def test_no_connection_means_no_embedder() -> None:
    assert remote_embedder(None, "sk-secret") is None


def test_anthropic_has_no_embeddings_endpoint() -> None:
    assert remote_embedder(_conn(Protocol.ANTHROPIC), "sk-secret") is None


def test_unknown_protocol_is_tried() -> None:
    assert isinstance(remote_embedder(_conn(Protocol.UNKNOWN), "sk-secret"), RemoteEmbedder)


async def test_ollama_is_used_for_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike transcription (a hosted audio endpoint), ollama serves an
    OpenAI-compatible ``/v1/embeddings`` route at the same ``/v1`` base URL
    this codebase already gives it, and it is exactly the loopback,
    internal-only connection this feature runs on — so it is included here."""
    embedder = remote_embedder(_ollama_conn(), None)
    assert isinstance(embedder, RemoteEmbedder)

    _patched(monkeypatch, httpx.MockTransport(_handler_ok()))
    result = await embedder.embed(["only text"])
    assert result == ((0.0, 1.0, 2.0),)


def test_model_is_overridable_without_a_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_EMBED_MODEL", "gateway-embed-v2")
    e = remote_embedder(_conn(), "sk-secret")
    assert e is not None
    assert e._model == "gateway-embed-v2"
