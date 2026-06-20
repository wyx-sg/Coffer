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
    # KB5: the title is prepended only to the EMBEDDED text; the FTS passage stays
    # raw, so the title (surfaced separately via ``Passage.title``) never leaks
    # into ``Passage.text``.
    assert hits[0].text == "the quick brown fox jumps"
    assert "Alpha" not in hits[0].text


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


@pytest.mark.asyncio
async def test_keyword_search_matches_cjk_via_trigram(substrate) -> None:
    """unicode61 made a no-space Chinese run one token, so a CJK query never
    matched; the trigram tokenizer matches the substring."""
    await substrate.repo.upsert_document(_doc("d1", "kb1", "向量"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["向量检索使用语义嵌入模型来匹配查询"], None)
    hits = await idx.keyword_search("kb1", "向量检索", top_k=5)
    assert {h.document_id for h in hits} == {"d1"}


@pytest.mark.asyncio
async def test_short_cjk_query_uses_like_fallback(substrate) -> None:
    """A < 3-character query produces no trigram tokens; keyword_search falls
    back to a substring (LIKE) scan rather than returning empty."""
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["向量检索很有用"], None)
    hits = await idx.keyword_search("kb1", "向量", top_k=5)
    assert {h.document_id for h in hits} == {"d1"}
    # The fallback is still substring-scoped: a non-substring short query misses.
    assert await idx.keyword_search("kb1", "查询", top_k=5) == []


@pytest.mark.asyncio
async def test_multi_term_and_first_ranks_all_terms_above_one(substrate) -> None:
    """A multi-term query is AND-first: a chunk matching ALL terms outranks a
    chunk matching only one of them, so a small top_k isn't diluted by the
    common term's bm25. docB stays findable but after docA (OR fallback fills
    the remainder)."""
    await substrate.repo.upsert_document(_doc("dA", "kb1", "Both"))
    await substrate.repo.upsert_document(_doc("dB", "kb1", "One"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("dA", ["alpha beta together here"], None)
    await idx.upsert_chunks("dB", ["alpha alpha alpha alpha alpha"], None)

    hits = await idx.keyword_search("kb1", "alpha beta", top_k=5)
    assert hits[0].document_id == "dA"
    # docB is still recalled via the OR fallback (AND alone returned < top_k).
    assert "dB" in {h.document_id for h in hits}


@pytest.mark.asyncio
async def test_multi_term_falls_back_to_or_when_and_empty(substrate) -> None:
    """When the terms never co-occur in any single chunk the AND query returns
    nothing; keyword search then widens to OR so single-term matches still
    surface rather than returning empty."""
    await substrate.repo.upsert_document(_doc("d1", "kb1", "A"))
    await substrate.repo.upsert_document(_doc("d2", "kb1", "B"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["gamma only content here"], None)
    await idx.upsert_chunks("d2", ["delta only content here"], None)

    # "gamma" and "delta" never share a chunk → AND is empty → OR fallback.
    hits = await idx.keyword_search("kb1", "gamma delta", top_k=5)
    assert hits  # non-empty
    assert {h.document_id for h in hits} == {"d1", "d2"}


@pytest.mark.asyncio
async def test_single_term_query_unchanged(substrate) -> None:
    """A one-term query behaves exactly as before (AND == OR, single search)."""
    await substrate.repo.upsert_document(_doc("d1", "kb1", "Alpha"))
    await substrate.repo.upsert_document(_doc("d2", "kb1", "Beta"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("d1", ["the quick brown fox jumps", "lazy dog sleeps"], None)
    await idx.upsert_chunks("d2", ["unrelated content about cats"], None)

    hits = await idx.keyword_search("kb1", "fox", top_k=5)
    assert len(hits) == 1
    assert hits[0].document_id == "d1"
    assert "fox" in hits[0].text


@pytest.mark.asyncio
async def test_multi_term_dedupes_across_and_or(substrate) -> None:
    """An AND hit must not reappear as an OR-only hit: the merge dedupes by
    chunk identity (document_id, position) and keeps the AND hit first."""
    await substrate.repo.upsert_document(_doc("dA", "kb1", "Both"))
    await substrate.repo.upsert_document(_doc("dB", "kb1", "One"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("dA", ["sigma tau co-occur"], None)
    await idx.upsert_chunks("dB", ["sigma alone"], None)

    hits = await idx.keyword_search("kb1", "sigma tau", top_k=5)
    keys = [(h.document_id, h.position) for h in hits]
    assert len(keys) == len(set(keys))  # no duplicate chunk
    assert keys[0] == ("dA", 0)  # AND hit first


@pytest.mark.asyncio
async def test_and_sufficient_skips_or_widening(substrate) -> None:
    """When AND already fills top_k, the OR query is skipped: a doc matching only
    ONE term never appears — the precise all-term hits win."""
    await substrate.repo.upsert_document(_doc("dA", "kb1", "Both A"))
    await substrate.repo.upsert_document(_doc("dB", "kb1", "Both B"))
    await substrate.repo.upsert_document(_doc("dC", "kb1", "One"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("dA", ["sigma tau both here"], None)
    await idx.upsert_chunks("dB", ["sigma tau also both"], None)
    await idx.upsert_chunks("dC", ["sigma only here"], None)  # one term only

    # top_k=2: the two AND hits fill it, so the OR-only dC must not surface.
    hits = await idx.keyword_search("kb1", "sigma tau", top_k=2)
    docs = {h.document_id for h in hits}
    assert docs == {"dA", "dB"}
    assert "dC" not in docs
