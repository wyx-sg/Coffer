"""Integration: FTS5 keyword index (bm25 ranking) over real SQLite."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    KIND_MEMORY,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)


def _doc(doc_id: str, resource: str, title: str, kind: str = KIND_KNOWLEDGE_BASE) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=doc_id,
        kind=kind,
        resource_name=resource,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title=title,
        content_sha256="x",
        source_mode="converted",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_keyword_search_returns_ranked_passages(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1", "Alpha"))
    await substrate.repo.upsert_document(_doc("d2", "kb1", "Beta"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["the quick brown fox jumps", "lazy dog sleeps"], None)
    await idx.upsert_chunks("d2", ["unrelated content about cats"], None)

    hits = await idx.keyword_search("kb1", "fox", top_k=5)
    assert len(hits) == 1
    assert hits[0].document_id == "d1"
    assert "fox" in hits[0].text
    assert hits[0].title == "Alpha"
    assert hits[0].score is not None


@pytest.mark.asyncio
async def test_keyword_search_scopes_by_resource(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    await substrate.repo.upsert_document(_doc("d2", "kb2", "B"))
    idx1 = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    idx2 = substrate.index(KIND_KNOWLEDGE_BASE, "kb2")
    await idx1.upsert_chunks("d1", ["shared keyword apple"], None)
    await idx2.upsert_chunks("d2", ["shared keyword apple"], None)

    hits = await idx1.keyword_search("kb1", "apple", top_k=5)
    assert {h.document_id for h in hits} == {"d1"}


@pytest.mark.asyncio
async def test_keyword_search_scopes_by_kind(substrate) -> None:
    """A KB and a memory store may share a resource name (the unique constraint
    is on (kind, name)); keyword search must not leak across kinds."""
    await substrate.repo.upsert_document(_doc("kbdoc", "foo", "KB", KIND_KNOWLEDGE_BASE))
    await substrate.repo.upsert_document(_doc("memdoc", "foo", "MEM", KIND_MEMORY))
    kb_idx = substrate.index(KIND_KNOWLEDGE_BASE, "foo")
    mem_idx = substrate.index(KIND_MEMORY, "foo")
    await kb_idx.upsert_chunks("kbdoc", ["knowledge pineapple content"], None)
    await mem_idx.upsert_chunks("memdoc", ["memory pineapple content"], None)

    kb_hits = await kb_idx.keyword_search("foo", "pineapple", top_k=5)
    mem_hits = await mem_idx.keyword_search("foo", "pineapple", top_k=5)
    assert {h.document_id for h in kb_hits} == {"kbdoc"}
    assert {h.document_id for h in mem_hits} == {"memdoc"}
    assert {h.title for h in kb_hits} == {"KB"}
    assert {h.title for h in mem_hits} == {"MEM"}


@pytest.mark.asyncio
async def test_same_document_id_in_two_stores_does_not_collide(substrate) -> None:
    """Document ids are content-addressed, so the same file ingested into two
    stores repeats its id. Indexing the second store must not steal/re-tag the
    first store's chunk + FTS rows, and deleting the document from one store
    must not wipe the other's index (P0: cross-KB chunk-id collision)."""
    await substrate.repo.upsert_document(_doc("dd", "kb1", "One"))
    await substrate.repo.upsert_document(_doc("dd", "kb2", "Two"))
    idx1 = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    idx2 = substrate.index(KIND_KNOWLEDGE_BASE, "kb2")
    await idx1.upsert_chunks("dd", ["shared mango content"], None)
    await idx2.upsert_chunks("dd", ["shared mango content"], None)

    kb1_hits = await idx1.keyword_search("kb1", "mango", top_k=5)
    kb2_hits = await idx2.keyword_search("kb2", "mango", top_k=5)
    assert {h.document_id for h in kb1_hits} == {"dd"}
    assert {h.document_id for h in kb2_hits} == {"dd"}
    assert {h.title for h in kb1_hits} == {"One"}
    assert {h.title for h in kb2_hits} == {"Two"}

    # Deleting the shared document from kb2 must leave kb1's index intact.
    await idx2.delete_chunks("dd")
    kb1_after = await idx1.keyword_search("kb1", "mango", top_k=5)
    assert {h.document_id for h in kb1_after} == {"dd"}
    assert await idx2.keyword_search("kb2", "mango", top_k=5) == []


@pytest.mark.asyncio
async def test_reindex_replaces_chunks(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["original banana text"], None)
    assert len(await idx.keyword_search("kb1", "banana", top_k=5)) == 1
    # Re-index with new content; old chunk must be gone.
    await idx.upsert_chunks("d1", ["replaced cherry text"], None)
    assert await idx.keyword_search("kb1", "banana", top_k=5) == []
    assert len(await idx.keyword_search("kb1", "cherry", top_k=5)) == 1


@pytest.mark.asyncio
async def test_delete_chunks_clears_fts(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["grape soda"], None)
    await idx.delete_chunks("d1")
    assert await idx.keyword_search("kb1", "grape", top_k=5) == []


@pytest.mark.asyncio
async def test_punctuation_in_query_is_safe(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["the make release target"], None)
    # A query with FTS operators must not raise.
    hits = await idx.keyword_search("kb1", "make OR (release", top_k=5)
    assert any("make" in h.text for h in hits)
