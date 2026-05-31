"""TEST22-KW: keyword (no-embedding) search store + per-KB dispatcher.

Covers spec 006-knowledge-base FR-016 (search modes): a KB in
``search_mode="keyword"`` is searchable with no embedding model — ingest
stores extracted text on disk and search ranks passages by term frequency.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.infrastructure.knowledge_base.dispatching_store import (
    DispatchingKnowledgeBaseStore,
)
from coffer.infrastructure.knowledge_base.keyword_store import KeywordKnowledgeBaseStore
from coffer.infrastructure.knowledge_base.paths import kb_text_dir


def _doc(doc_id: str, filename: str) -> Document:
    return Document(
        id=doc_id,
        kb_name="kb1",
        filename=filename,
        extension=".md",
        size_bytes=10,
        sha256="0" * 64,
        chunk_count=0,
        ingested_at=datetime.now(tz=UTC),
    )


@pytest.fixture
def kb_root_tmp(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("COFFER_KB_ROOT", str(tmp_path / "kb"))
    return tmp_path


async def test_keyword_search_ranks_by_term_frequency(kb_root_tmp: pathlib.Path) -> None:
    store = KeywordKnowledgeBaseStore(text_dir=kb_text_dir)
    await store.open("kb1", KnowledgeBaseConfig(search_mode="keyword"))
    await store.ingest(
        "kb1",
        _doc("d1", "retry.md"),
        "The retry policy retries failed calls.\n\nRetry uses exponential backoff.",
    )
    await store.ingest("kb1", _doc("d2", "intro.md"), "An introduction. Nothing relevant here.")

    hits = await store.search("kb1", "retry", top_k=5)

    assert hits, "expected keyword hits"
    assert hits[0].document_id == "d1"
    assert hits[0].filename == "retry.md"
    # 'retry' appears 3x across d1 (case-insensitive) — top passage scores >= 1.
    assert hits[0].score >= 1.0
    assert all(h.document_id != "d2" for h in hits)


async def test_keyword_search_blank_query_returns_nothing(kb_root_tmp: pathlib.Path) -> None:
    store = KeywordKnowledgeBaseStore(text_dir=kb_text_dir)
    await store.open("kb1", KnowledgeBaseConfig())
    await store.ingest("kb1", _doc("d1", "a.md"), "hello world")
    assert list(await store.search("kb1", "   ", top_k=5)) == []


async def test_keyword_delete_then_drop(kb_root_tmp: pathlib.Path) -> None:
    store = KeywordKnowledgeBaseStore(text_dir=kb_text_dir)
    await store.open("kb1", KnowledgeBaseConfig())
    await store.ingest("kb1", _doc("d1", "a.md"), "alpha beta")
    await store.ingest("kb1", _doc("d2", "b.md"), "alpha gamma")

    await store.delete_document("kb1", "d1")
    hits = await store.search("kb1", "alpha", top_k=5)
    assert {h.document_id for h in hits} == {"d2"}

    await store.drop("kb1")
    assert list(await store.search("kb1", "alpha", top_k=5)) == []


class _RecordingStore:
    """Minimal KnowledgeBaseStore spy for dispatcher routing tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        self.calls.append(("open", kb_name))

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        self.calls.append(("ingest", kb_name))
        return 1

    async def search(self, kb_name: str, query: str, top_k: int) -> list:
        self.calls.append(("search", kb_name))
        return []

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        self.calls.append(("delete", kb_name))

    async def drop(self, kb_name: str) -> None:
        self.calls.append(("drop", kb_name))

    async def close(self) -> None:
        self.calls.append(("close", ""))


async def test_dispatcher_routes_search_by_mode() -> None:
    kw, sem = _RecordingStore(), _RecordingStore()
    d = DispatchingKnowledgeBaseStore(keyword=kw, semantic=sem)

    await d.open("kw_kb", KnowledgeBaseConfig(search_mode="keyword"))
    await d.open("sem_kb", KnowledgeBaseConfig(search_mode="semantic"))
    await d.search("kw_kb", "q", 5)
    await d.search("sem_kb", "q", 5)

    assert ("search", "kw_kb") in kw.calls
    assert ("search", "kw_kb") not in sem.calls
    assert ("search", "sem_kb") in sem.calls
    assert ("search", "sem_kb") not in kw.calls


async def test_dispatcher_teardown_fans_out_to_both() -> None:
    kw, sem = _RecordingStore(), _RecordingStore()
    d = DispatchingKnowledgeBaseStore(keyword=kw, semantic=sem)

    # delete/drop happen without a prior open() — both backends must be hit.
    await d.delete_document("kb1", "doc1")
    await d.drop("kb1")

    assert ("delete", "kb1") in kw.calls and ("delete", "kb1") in sem.calls
    assert ("drop", "kb1") in kw.calls and ("drop", "kb1") in sem.calls
