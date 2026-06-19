"""Unit: the shared retrieval facade — keyword↔vector + the fallback flag.

Pure (fake index + fake embedder); no I/O.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.retrieval import Passage, StoreRef


class FakeIndex:
    def __init__(self, *, keyword=None, vector=None):
        self._keyword = keyword or []
        self._vector = vector or []
        self.vector_called = False

    async def upsert_chunks(self, document_id, chunks, vectors):
        return len(chunks)

    async def delete_chunks(self, document_id):
        return None

    async def keyword_search(self, resource_name, query, top_k):
        return self._keyword[:top_k]

    async def vector_search(self, resource_name, vector, top_k):
        self.vector_called = True
        return self._vector[:top_k]


class FakeEmbedder:
    def __init__(self, dimensions=8, fail=False):
        self._dim = dimensions
        self._fail = fail

    @property
    def dimensions(self):
        return self._dim

    async def embed(self, texts):
        if self._fail:
            raise EngineUnavailable("embedding", "no provider")
        return [[1.0] * self._dim for _ in texts]


def _store() -> StoreRef:
    return StoreRef(kind="knowledge_base", resource_name="kb1", project_id="0" * 26, docs_dir="/x")


def _passage(doc_id: str) -> Passage:
    return Passage(document_id=doc_id, title="T", text="text", score=1.0, position=0)


def _facade(index: FakeIndex, *, embedder=None):
    return KnowledgeRetrieval(
        index_factory=lambda kind, rn, *, dimensions: index,
        grep=None,  # not used in these tests
        embedder_factory=lambda config: embedder or FakeEmbedder(),
    )


def _embedding() -> EmbeddingConfig:
    return EmbeddingConfig(provider="local", model="m", dimensions=8)


@pytest.mark.asyncio
async def test_keyword_mode_returns_keyword_passages() -> None:
    index = FakeIndex(keyword=[_passage("k1")])
    result = await _facade(index).search(_store(), "q", mode="keyword", top_k=5)
    assert result.mode == "keyword"
    assert result.fallback is None
    assert [p.document_id for p in result.passages] == ["k1"]


@pytest.mark.asyncio
async def test_vector_mode_uses_vector_search() -> None:
    index = FakeIndex(vector=[_passage("v1")])
    result = await _facade(index).search(
        _store(), "q", mode="vector", top_k=5, embedding=_embedding()
    )
    assert result.mode == "vector"
    assert result.fallback is None
    assert index.vector_called
    assert [p.document_id for p in result.passages] == ["v1"]


@pytest.mark.asyncio
async def test_vector_without_embedding_config_falls_back_flagged() -> None:
    index = FakeIndex(keyword=[_passage("k1")], vector=[_passage("v1")])
    result = await _facade(index).search(_store(), "q", mode="vector", top_k=5, embedding=None)
    assert result.mode == "vector"
    assert result.fallback == "keyword"
    assert not index.vector_called
    assert [p.document_id for p in result.passages] == ["k1"]


@pytest.mark.asyncio
async def test_vector_with_unavailable_provider_falls_back_flagged() -> None:
    index = FakeIndex(keyword=[_passage("k1")])
    facade = _facade(index, embedder=FakeEmbedder(fail=True))
    result = await facade.search(_store(), "q", mode="vector", top_k=5, embedding=_embedding())
    assert result.fallback == "keyword"
    assert not index.vector_called
    assert [p.document_id for p in result.passages] == ["k1"]


@pytest.mark.asyncio
async def test_grep_mode_is_rejected_as_passage_mode() -> None:
    with pytest.raises(ValueError, match="grep"):
        await _facade(FakeIndex()).search(_store(), "q", mode="grep", top_k=5)


class DroppableIndex(FakeIndex):
    """A FakeIndex that also supports per-store substrate teardown."""

    def __init__(self) -> None:
        super().__init__()
        self.dropped = False

    async def drop_store(self) -> None:
        self.dropped = True


@pytest.mark.asyncio
async def test_drop_store_invokes_index_teardown() -> None:
    # A droppable index has its per-store substrate (sqlite-vec table) dropped
    # on store delete (finding #6).
    index = DroppableIndex()
    await _facade(index).drop_store(_store(), dimensions=8)
    assert index.dropped is True


@pytest.mark.asyncio
async def test_drop_store_is_noop_for_keyword_only_index() -> None:
    # A keyword/grep-only index has no drop_store; the facade must not raise.
    index = FakeIndex()  # no drop_store attribute
    await _facade(index).drop_store(_store(), dimensions=None)
