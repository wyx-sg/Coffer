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
        self.vector_upserts = []
        self.deletes = []

    async def upsert_chunks(self, document_id, chunks, vectors):
        self.upserts.append((document_id, list(chunks), vectors))
        return len(chunks)

    async def upsert_vectors(self, document_id, vectors):
        self.vector_upserts.append((document_id, [list(v) for v in vectors]))

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
        #: The exact texts handed to ``embed`` — lets a test assert the title was
        #: prepended to the EMBEDDED text (KB5) while the stored chunks stay raw.
        self.embedded: list[str] = []

    @property
    def dimensions(self):
        return self._dim

    async def embed(self, texts):
        if self._fail:
            raise EngineUnavailable("embedding", "down")
        self.embedded = list(texts)
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
async def test_embed_failure_keeps_real_sha_and_marks_pending() -> None:
    """A degraded embed keeps the REAL content sha (decoupled, KB8) and flags
    ``embed_pending`` so the retry state lives on its own column — the sha gate
    no longer churns the whole degraded corpus on every scan."""
    index = RecordingIndex()
    failing = await _reindexer(FakeEmbedder(fail=True)).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
    )
    assert failing.changed is True
    assert failing.embedded is False
    assert failing.embed_pending is True
    assert failing.content_sha256 == content_sha256("alpha\n\nbeta")  # real sha, not ""


@pytest.mark.asyncio
async def test_pending_retry_embeds_vectors_only_without_rechunk() -> None:
    """A second reindex with unchanged content but ``previous_embed_pending`` and
    the provider now UP retries JUST the embed: it calls ``upsert_vectors`` (NOT
    ``upsert_chunks``) so FTS/chunks are never rewritten (KB8 churn fix)."""
    index = RecordingIndex()
    sha = content_sha256("alpha\n\nbeta")
    retried = await _reindexer().reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=sha,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
        previous_embed_pending=True,
    )
    assert retried.changed is False
    assert retried.embedded is True
    assert retried.embed_pending is False
    assert retried.content_sha256 == sha
    # Only vectors were upserted — chunks/FTS untouched (no churn).
    assert index.upserts == []
    assert len(index.vector_upserts) == 1
    assert index.vector_upserts[0][0] == "d1"
    assert len(index.vector_upserts[0][1]) == 2  # one vector per chunk


@pytest.mark.asyncio
async def test_unchanged_not_pending_is_true_noop_no_chunker_or_embed() -> None:
    """Unchanged content + not pending is a TRUE no-op: the chunker and embedder
    are never invoked, and nothing is upserted."""
    chunker_calls: list[str] = []

    def _tracking_chunker(md: str) -> list[str]:
        chunker_calls.append(md)
        return _chunker(md)

    embedder = FakeEmbedder()
    index = RecordingIndex()
    sha = content_sha256("alpha\n\nbeta")
    outcome = await _reindexer(embedder).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=sha,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_tracking_chunker,
        previous_embed_pending=False,
    )
    assert outcome.changed is False
    assert outcome.embed_pending is False
    assert chunker_calls == []  # chunker never called
    assert index.upserts == []
    assert index.vector_upserts == []


@pytest.mark.asyncio
async def test_title_prepended_to_embedded_text_only_fts_stays_raw() -> None:
    """KB5: the document title is prepended as topic context to every EMBEDDED
    text, but the chunks landing in FTS / the chunk rows stay RAW (no prefix), so
    ``Passage.text`` is never polluted (title is surfaced via ``Passage.title``)."""
    embedder = FakeEmbedder()
    index = RecordingIndex()
    outcome = await _reindexer(embedder).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
        title="My Title",
    )
    assert outcome.changed is True
    # Every embedded text carries the title context prefix.
    assert embedder.embedded == ["My Title\n\nalpha", "My Title\n\nbeta"]
    assert all(t.startswith("My Title\n\n") for t in embedder.embedded)
    # FTS / chunk rows received the RAW chunks (no title prefix).
    assert index.upserts[0][1] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_empty_title_embeds_raw_chunk_unchanged() -> None:
    """No title (default ``""``) ⇒ the embedded text is the raw chunk, unchanged."""
    embedder = FakeEmbedder()
    index = RecordingIndex()
    await _reindexer(embedder).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=None,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
        title="",
    )
    assert embedder.embedded == ["alpha", "beta"]  # no prefix
    assert index.upserts[0][1] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_pending_retry_prepends_title_to_reembedded_text() -> None:
    """KB5 + KB8: the retry-embed-only path (unchanged content, was pending,
    provider now up) ALSO prepends the title to the re-embedded text, so the
    retried vectors are consistent with the content-changed path."""
    embedder = FakeEmbedder()
    index = RecordingIndex()
    sha = content_sha256("alpha\n\nbeta")
    retried = await _reindexer(embedder).reindex(
        index=index,
        markdown="alpha\n\nbeta",
        previous_sha=sha,
        embedding=EmbeddingConfig(provider="local", model="m", dimensions=4),
        doc_id="d1",
        chunker=_chunker,
        title="My Title",
        previous_embed_pending=True,
    )
    assert retried.changed is False
    assert retried.embedded is True
    assert embedder.embedded == ["My Title\n\nalpha", "My Title\n\nbeta"]
    # Retry path writes ONLY vectors — chunks/FTS untouched (KB8 no-churn).
    assert index.upserts == []
    assert len(index.vector_upserts) == 1
