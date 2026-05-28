"""Real-engine smoke test for `LlamaIndexKnowledgeBaseStore`.

The rest of the KB suite runs against `FakeKnowledgeBaseStore`; this file
exercises the actual LlamaIndex adapter end-to-end. It is heavy (loads a
HuggingFace embedding model, downloading it on first run), so it is gated:
it only runs when `COFFER_RUN_ENGINE_TESTS=1`.

    COFFER_RUN_ENGINE_TESTS=1 pytest tests/integration/knowledge_base/test_llamaindex_store.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document

pytestmark = [
    pytest.mark.engine,
    pytest.mark.skipif(
        os.environ.get("COFFER_RUN_ENGINE_TESTS") != "1",
        reason="real-engine test; set COFFER_RUN_ENGINE_TESTS=1 to run",
    ),
]


def _doc(doc_id: str, filename: str, body: bytes) -> Document:
    return Document(
        id=doc_id,
        kb_name="kb1",
        filename=filename,
        extension=".md",
        size_bytes=len(body),
        sha256=doc_id * 8,
        chunk_count=0,
        ingested_at=datetime.now(tz=UTC),
    )


async def test_open_ingest_search_delete_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFER_KB_ROOT", str(tmp_path / "kb"))
    from coffer.infrastructure.knowledge_base.llamaindex_store import (
        LlamaIndexKnowledgeBaseStore,
    )

    config = KnowledgeBaseConfig()
    store = LlamaIndexKnowledgeBaseStore()

    # open() must populate the cached config so a later ingest/search needs
    # no second open() — this is the regression guard for the "first ingest
    # after a restart" bug.
    await store.open("kb1", config)

    n1 = await store.ingest("kb1", _doc("a", "fox.md", b"x"), "the quick brown fox jumps")
    n2 = await store.ingest("kb1", _doc("b", "cats.md", b"y"), "cats are independent animals")
    assert n1 >= 1 and n2 >= 1

    hits = await store.search("kb1", "fox", top_k=3)
    assert any(h.document_id == "a" for h in hits), hits

    await store.delete_document("kb1", "a")

    # Drop the in-memory index, re-open from disk: the surviving document
    # must still be searchable (validates the per-index embed_model is
    # carried through persist/load — no reliance on global Settings).
    await store.drop("kb1")
    await store.open("kb1", config)
    hits2 = await store.search("kb1", "cats", top_k=3)
    assert any(h.document_id == "b" for h in hits2), hits2
    assert all(h.document_id != "a" for h in hits2), "deleted doc resurfaced"

    await store.close()
