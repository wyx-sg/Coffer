"""Unit: the single idempotent re-index routine (sha no-op gate + embed).

Pure (fake index + fake embedder); no I/O.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.reindex import Reindexer, content_sha256
from coffer.domain.errors import EngineUnavailable
from coffer.domain.knowledge.embedder import EmbeddingConfig


class RecordingIndex:
    def __init__(self):
        self.upserts = []
        self.deletes = []

    async def upsert_chunks(self, document_id, chunks, vectors):
        self.upserts.append((document_id, list(chunks), vectors))
        return len(chunks)

    async def delete_chunks(self, document_id):
        self.deletes.append(document_id)

    async def keyword_search(self, *a, **k):
        return []

    async def vector_search(self, *a, **k):
        return []


class FakeEmbedder:
    def __init__(self, dimensions=4, fail=False):
        self._dim = dimensions
        self._fail = fail

    @property
    def dimensions(self):
        return self._dim

    async def embed(self, texts):
        if self._fail:
            raise EngineUnavailable("embedding", "down")
        return [[0.5] * self._dim for _ in texts]


def _chunker(md: str) -> list[str]:
    return [s for s in md.split("\n\n") if s.strip()]


def _reindexer(embedder=None) -> Reindexer:
    return Reindexer(embedder_factory=lambda config: embedder or FakeEmbedder())


@pytest.mark.asyncio
async def test_unchanged_sha_is_noop() -> None:
    index = RecordingIndex()
    sha = content_sha256("hello world")
    outcome = await _reindexer().reindex(
        index=index,
        markdown="hello world",
        previous_sha=sha,
        embedding=None,
        doc_id="d1",
        chunker=_chunker,
    )
    assert outcome.changed is False
    assert index.upserts == []
    assert index.deletes == []


@pytest.mark.asyncio
async def test_changed_content_rechunks() -> None:
    index = RecordingIndex()
    outcome = await _reindexer().reindex(
        index=index,
        markdown="para one\n\npara two",
        previous_sha=content_sha256("different"),
        embedding=None,
        doc_id="d1",
        chunker=_chunker,
    )
    assert outcome.changed is True
    assert outcome.chunk_count == 2
    assert index.upserts[0][1] == ["para one", "para two"]
    assert index.upserts[0][2] is None  # no vectors without embedding


@pytest.mark.asyncio
async def test_first_index_with_none_previous_sha_indexes() -> None:
    index = RecordingIndex()
    outcome = await _reindexer().reindex(
        index=index,
        markdown="content here",
        previous_sha=None,
        embedding=None,
        doc_id="d1",
        chunker=_chunker,
    )
    assert outcome.changed is True
    assert len(index.upserts) == 1


@pytest.mark.asyncio
async def test_embedding_produces_vectors() -> None:
    index = RecordingIndex()
    outcome = await _reindexer().reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
    )
    assert outcome.embedded is True
    assert index.upserts[0][2] is not None
    assert len(index.upserts[0][2]) == 2


@pytest.mark.asyncio
async def test_embedding_unavailable_degrades_to_keyword_only() -> None:
    index = RecordingIndex()
    outcome = await _reindexer(FakeEmbedder(fail=True)).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
    )
    # The write must not fail; vectors are None (keyword-only).
    assert outcome.changed is True
    assert outcome.embedded is False
    assert index.upserts[0][2] is None


@pytest.mark.asyncio
async def test_embed_failure_does_not_advance_the_sha_gate() -> None:
    """A transient embed failure must stay retryable: the outcome carries an
    empty sha so the persisted row mismatches the file on the next reconcile
    and the embed is retried (review M1)."""
    index = RecordingIndex()
    failing = await _reindexer(FakeEmbedder(fail=True)).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
    )
    assert failing.embedded is False
    assert failing.content_sha256 == ""  # caller persists a never-matching sha

    # Next reconcile: previous_sha="" mismatches → retried; embedder now works.
    retried = await _reindexer().reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=failing.content_sha256 or None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
    )
    assert retried.embedded is True
    assert retried.content_sha256 == content_sha256("alpha\n\nbeta")
