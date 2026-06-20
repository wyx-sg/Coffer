"""Integration: the KB application service over the real substrate."""

from __future__ import annotations

import pytest

from coffer.domain.errors import IngestRejected, ReconversionBlocked
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge import paths

pytestmark = pytest.mark.asyncio


async def _ingest(kb, name: str, filename: str, data: bytes, **kw):
    return await kb.service.ingest_bytes(
        kb_name=name, filename=filename, raw_bytes=data, actor="user", **kw
    )


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="create a knowledge base")
async def test_create_kb_makes_dirs(kb) -> None:
    await kb.create_kb("design-notes")
    config = await kb.service.get_kb_config("design-notes")
    assert config.default_mode == "keyword"
    listed = await kb.resources.list(kind="knowledge_base")
    assert [r.name for r in listed] == ["design-notes"]


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="ingest converts any format to markdown"
)
async def test_ingest_converts_csv_to_markdown(kb) -> None:
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "data.csv", b"a,b\n1,2\n")
    assert doc.source_mode == "converted"
    assert doc.metadata["original_format"] == "csv"
    # docs/<id>.md exists with frontmatter + a markdown table.
    md = paths.doc_path("kb1", doc.id)
    assert md.exists()
    text = md.read_text()
    assert "source_mode: converted" in text
    assert "| a | b |" in text
    # raw original preserved.
    assert paths.raw_path("kb1", doc.id, ".csv").exists()
    # a documents row + chunks exist.
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 1
    assert await kb.documents.count_chunks("knowledge_base", "kb1") >= 1


async def test_ingest_rejects_empty(kb) -> None:
    await kb.create_kb("kb1")
    with pytest.raises(IngestRejected) as exc:
        await _ingest(kb, "kb1", "empty.md", b"")
    assert exc.value.reason == "empty"


async def test_ingest_rejects_oversize(kb) -> None:
    await kb.create_kb("kb1", config={"max_document_bytes": 1024})
    with pytest.raises(IngestRejected) as exc:
        await _ingest(kb, "kb1", "big.md", b"x" * 2048)
    assert exc.value.reason == "too_large"


async def test_ingest_rejects_unsupported_type(kb) -> None:
    await kb.create_kb("kb1")
    with pytest.raises(IngestRejected) as exc:
        await _ingest(kb, "kb1", "thing.zzz", b"\x00\x01\x02binary")
    assert exc.value.reason == "unsupported_type"


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="re-upload of an identical file is a no-op"
)
async def test_reupload_identical_file_is_noop(kb) -> None:
    await kb.create_kb("kb1")
    first = await _ingest(kb, "kb1", "a.md", b"# Hello\n\nworld")
    # A byte-identical re-upload (matched by filename) is an idempotent no-op:
    # same document id, still one document, no error — no replace flag needed.
    again = await _ingest(kb, "kb1", "a.md", b"# Hello\n\nworld")
    assert again.id == first.id
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 1
    # The no-op re-uploads NOTHING, so no second audit event is recorded.
    events = await kb.audit.query(kind="knowledge_base", name="kb1", limit=50)
    types = [e.event_type for e in events]
    assert types.count("kb_document_ingested") == 1
    assert "kb_document_updated" not in types


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="re-upload of an updated file updates the document in place",
)
async def test_reupload_updated_file_updates_in_place(kb) -> None:
    await kb.create_kb("kb1")
    first = await _ingest(kb, "kb1", "a.md", b"# Hello\n\noriginal apple body")
    # A CHANGED re-upload of the same filename is rejected without replace=true,
    with pytest.raises(IngestRejected) as exc:
        await _ingest(kb, "kb1", "a.md", b"# Hello\n\nchanged banana body")
    assert exc.value.reason == "duplicate"
    # ...and updates the SAME document in place with replace=true (no duplicate).
    updated = await _ingest(kb, "kb1", "a.md", b"# Hello\n\nchanged banana body", replace=True)
    assert updated.id == first.id
    assert updated.source_mode == "converted"
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 1
    # New content searchable; old content gone.
    assert (await kb.service.search(kb_name="kb1", query="apple", top_k=5)).passages == ()
    assert len((await kb.service.search(kb_name="kb1", query="banana", top_k=5)).passages) == 1


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="ingest converts any format to markdown"
)
async def test_doc_id_is_ulid_not_content_hash(kb) -> None:
    """ADR-028: the doc id is a stable ULID (26-char Crockford base32), not the
    source sha256 prefix; the sha is kept in metadata as provenance only."""
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# A\n\nbody")
    assert len(doc.id) == 26
    assert doc.id != doc.metadata["source_sha256"][:16]
    assert doc.metadata["source_sha256"]  # provenance retained


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="list documents in a knowledge base")
async def test_list_documents_paginated(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# Alpha\n\nthe alpha doc")
    await _ingest(kb, "kb1", "b.md", b"# Beta\n\nthe beta doc")
    docs, total = await kb.service.list_documents(kb_name="kb1", limit=1, offset=0)
    assert total == 2
    assert len(docs) == 1


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="keyword search returns ranked passages"
)
async def test_keyword_search_ranks(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "fox.md", b"# Fox\n\nthe quick brown fox jumps")
    await _ingest(kb, "kb1", "cat.md", b"# Cat\n\nunrelated content about cats")
    result = await kb.service.search(kb_name="kb1", query="fox", top_k=5)
    assert result.mode == "keyword"
    assert result.fallback is None
    assert len(result.passages) == 1
    assert "fox" in result.passages[0].text
    assert result.passages[0].title == "Fox"


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="keyword search matches CJK (Chinese) content"
)
async def test_keyword_search_matches_cjk(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "zh.md", "# 向量\n\n向量检索使用语义嵌入模型来匹配查询".encode())
    # Multi-character CJK query: served by the FTS5 trigram index (unicode61
    # would have returned nothing for a no-space Chinese run).
    result = await kb.service.search(kb_name="kb1", query="向量检索", top_k=5)
    assert result.mode == "keyword"
    assert any("向量检索" in p.text for p in result.passages)
    # Short (< 3 char) CJK query: trigram can't tokenize it, so the substring
    # (LIKE) fallback serves it instead of returning empty.
    short = await kb.service.search(kb_name="kb1", query="向量", top_k=5)
    assert any("向量" in p.text for p in short.passages)


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="grep returns file/line matches")
async def test_grep_returns_hits(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# Make\n\nthe make release target ships it")
    result = await kb.service.grep(kb_name="kb1", pattern="make release")
    assert len(result.hits) >= 1
    assert any("make release" in h.line for h in result.hits)
    assert all(h.line_number >= 1 for h in result.hits)
    assert result.truncated is False


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="vector search returns ranked passages")
async def test_vector_search_with_embedding(kb, vector_config) -> None:
    await kb.create_kb("kb1", config=vector_config)
    await _ingest(kb, "kb1", "a.md", b"# Alpha\n\nthe alpha passage about deploys")
    result = await kb.service.search(kb_name="kb1", query="deploys", top_k=5, mode="vector")
    assert result.mode == "vector"
    assert result.fallback is None
    assert len(result.passages) >= 1


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="vector falls back to keyword when embedding unconfigured",
)
async def test_vector_falls_back_to_keyword(kb) -> None:
    await kb.create_kb("kb1")  # keyword+grep only, no embedding
    await _ingest(kb, "kb1", "a.md", b"# Alpha\n\nthe alpha passage about deploys")
    result = await kb.service.search(kb_name="kb1", query="deploys", top_k=5, mode="vector")
    assert result.fallback == "keyword"
    assert len(result.passages) >= 1


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="edit a document and reindex")
async def test_edit_sets_edited_mode_and_reflects_in_search(kb) -> None:
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# Orig\n\noriginal banana content")
    assert len((await kb.service.search(kb_name="kb1", query="banana", top_k=5)).passages) == 1
    updated = await kb.service.edit_document(
        kb_name="kb1",
        document_id=doc.id,
        new_markdown="# Orig\n\nreplaced cherry content",
        actor="user",
    )
    assert updated.source_mode == "edited"
    assert (await kb.service.search(kb_name="kb1", query="banana", top_k=5)).passages == ()
    assert len((await kb.service.search(kb_name="kb1", query="cherry", top_k=5)).passages) == 1


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="external edit picked up by reindex-on-read"
)
async def test_out_of_band_edit_visible_on_reindex_on_read(kb) -> None:
    """The in-app viewer is read-only, so users edit ``docs/<id>.md`` directly
    in their external editor. The next read/search reconciles the on-disk file
    against the index by content hash and reflects the edit — no watcher, no
    explicit reindex call (FR-008a)."""
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# Orig\n\noriginal narwhal content")
    # Sanity: the original is indexed and searchable.
    assert len((await kb.service.search(kb_name="kb1", query="narwhal", top_k=5)).passages) == 1

    # Edit the normalized markdown body directly on disk (frontmatter intact),
    # bypassing the write API entirely — as an external editor would.
    md = paths.doc_path("kb1", doc.id)
    text = md.read_text()
    md.write_text(text.replace("original narwhal content", "edited platypus content"))

    # No explicit reindex: the search path reconciles on read.
    assert (await kb.service.search(kb_name="kb1", query="narwhal", top_k=5)).passages == ()
    hits = (await kb.service.search(kb_name="kb1", query="platypus", top_k=5)).passages
    assert len(hits) == 1
    assert "platypus" in hits[0].text


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="external edit picked up by reindex-on-read"
)
async def test_out_of_band_file_removal_pruned_on_read(kb) -> None:
    """A document whose markdown file is removed out-of-band is pruned from the
    index on the next read (files are truth in both directions)."""
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# Gone\n\nsoon to vanish content")
    assert len((await kb.service.search(kb_name="kb1", query="vanish", top_k=5)).passages) == 1
    paths.doc_path("kb1", doc.id).unlink()
    # Reconcile-on-read prunes the now-orphaned row.
    docs, total = await kb.service.list_documents(kb_name="kb1", limit=50, offset=0)
    assert total == 0
    assert docs == []
    assert (await kb.service.search(kb_name="kb1", query="vanish", top_k=5)).passages == ()


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="re-conversion blocked once edited")
async def test_reconversion_blocked_after_edit(kb) -> None:
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# T\n\nbody one")
    await kb.service.edit_document(
        kb_name="kb1", document_id=doc.id, new_markdown="# T\n\nhand edited", actor="user"
    )
    with pytest.raises(ReconversionBlocked):
        await kb.service.reconvert_document(kb_name="kb1", document_id=doc.id, actor="user")


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="changing chunk params re-indexes")
async def test_changing_chunk_params_reindexes(kb) -> None:
    await kb.create_kb("kb1")
    body = b"# Doc\n\n" + (b"alpha beta gamma delta " * 80)
    await _ingest(kb, "kb1", "a.md", body)
    before = await kb.documents.count_chunks("knowledge_base", "kb1")
    # Shrink the chunk size via update_config → on_update_config reindexes.
    await kb.resources.update_config(
        ref=ResourceRef("knowledge_base", "kb1"),
        new_config={
            "enabled_modes": ["keyword", "grep"],
            "default_mode": "keyword",
            "chunk_size": 64,
            "chunk_overlap": 8,
        },
        actor="user",
    )
    after = await kb.documents.count_chunks("knowledge_base", "kb1")
    assert after > before


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="changing embedding model re-embeds")
async def test_changing_embedding_model_re_embeds(kb, vector_config) -> None:
    await kb.create_kb("kb1", config=vector_config)
    await _ingest(kb, "kb1", "a.md", b"# Alpha\n\nthe alpha passage about deploys")
    # Vector search works before the model change.
    before = await kb.service.search(kb_name="kb1", query="deploys", top_k=5, mode="vector")
    assert before.fallback is None and len(before.passages) >= 1
    # Change the embedding model → on_update_config re-embeds the corpus.
    new_config = dict(vector_config)
    new_config["embedding"] = {**vector_config["embedding"], "model": "different-model"}
    await kb.resources.update_config(
        ref=ResourceRef("knowledge_base", "kb1"), new_config=new_config, actor="user"
    )
    # The model is mutable (not locked) and vector search still works post-re-embed.
    after = await kb.service.search(kb_name="kb1", query="deploys", top_k=5, mode="vector")
    assert after.fallback is None
    assert len(after.passages) >= 1
    config = await kb.service.get_kb_config("kb1")
    assert config.embedding is not None and config.embedding.model == "different-model"


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="delete a single document")
async def test_delete_document_removes_files_and_rows(kb) -> None:
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# A\n\ngrape soda")
    md = paths.doc_path("kb1", doc.id)
    raw = paths.raw_path("kb1", doc.id, ".md")
    assert md.exists() and raw.exists()
    await kb.service.delete_document(kb_name="kb1", document_id=doc.id, actor="user")
    assert not md.exists()
    assert not raw.exists()
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 0
    assert (await kb.service.search(kb_name="kb1", query="grape", top_k=5)).passages == ()


async def test_same_file_in_two_kbs_keeps_both_searchable(kb) -> None:
    """Doc ids are stable ULIDs (ADR-028), so the same file uploaded into two
    KBs gets two distinct ids — no cross-store dedup. The second ingest must not
    corrupt the first KB's index, and deleting the doc from one KB must not wipe
    the other's chunks (per-store chunk-id namespacing)."""
    await kb.create_kb("kb1")
    await kb.create_kb("kb2")
    payload = b"# Mango\n\nshared mango facts"
    doc1 = await _ingest(kb, "kb1", "mango.md", payload)
    doc2 = await _ingest(kb, "kb2", "mango.md", payload)
    assert doc1.id != doc2.id  # stable ULIDs: independent documents per store

    assert (await kb.service.search(kb_name="kb1", query="mango", top_k=5)).passages
    assert (await kb.service.search(kb_name="kb2", query="mango", top_k=5)).passages

    await kb.service.delete_document(kb_name="kb2", document_id=doc2.id, actor="user")
    assert (await kb.service.search(kb_name="kb1", query="mango", top_k=5)).passages
    assert (await kb.service.search(kb_name="kb2", query="mango", top_k=5)).passages == ()
    assert await kb.documents.count_chunks("knowledge_base", "kb1") >= 1


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="delete a knowledge base cleans up files and index"
)
async def test_delete_kb_cleans_up(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\nhello")
    kb_dir = paths.kb_dir("kb1")
    assert kb_dir.exists()
    from coffer.domain.resource import ResourceRef

    await kb.resources.delete(ResourceRef("knowledge_base", "kb1"), actor="user")
    assert not kb_dir.exists()
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 0


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="delete a knowledge base cleans up files and index"
)
async def test_delete_kb_purges_index_rows_and_vec_store(kb, vector_config) -> None:
    """SC-003: deleting a KB removes 100% of its SQLite rows — chunks and FTS
    rows too, and the per-store vector table is dropped."""
    from sqlalchemy import text

    from coffer.domain.resource import ResourceRef

    await kb.create_kb("kb1", config=vector_config)
    await _ingest(kb, "kb1", "a.md", b"# A\n\nhello vector world")
    assert await kb.documents.count_chunks("knowledge_base", "kb1") >= 1

    await kb.resources.delete(ResourceRef("knowledge_base", "kb1"), actor="user")

    assert await kb.documents.count_documents("knowledge_base", "kb1") == 0
    assert await kb.documents.count_chunks("knowledge_base", "kb1") == 0
    async with kb.sm() as session:
        fts_rows = (
            await session.execute(
                text("SELECT count(*) FROM documents_fts WHERE resource_name = 'kb1'")
            )
        ).scalar_one()
    assert fts_rows == 0
    vec = kb.vec_stores.get(("knowledge_base", "kb1"))
    assert vec is not None and vec.dropped


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="KB metrics report counts and disk usage"
)
async def test_metrics(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\nalpha content here")
    m = await kb.service.metrics(kb_name="kb1")
    assert m["document_count"] == 1
    assert m["chunk_count"] >= 1
    assert m["disk_bytes"] > 0
    assert "keyword" in m["enabled_modes"]


async def test_reindex_scan_is_noop_when_unchanged(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\nunchanged content")
    stats = await kb.service.reindex(kb_name="kb1", actor="user")
    # Content unchanged on disk → reindex is a no-op (skipped).
    assert stats["reindexed"] == 0
    assert stats["skipped"] == 1


async def test_reindex_rebuilds_from_files_after_index_drop(kb) -> None:
    """SC-005: dropping the chunk rows then reindexing rebuilds search state
    purely from the markdown files."""
    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# A\n\nphoenix rising content")
    index = kb.service._retrieval.index_for(  # type: ignore[attr-defined]
        kb.service._store_ref("kb1"),
        dimensions=None,  # type: ignore[attr-defined]
    )
    await index.delete_chunks(doc.id)
    assert (await kb.service.search(kb_name="kb1", query="phoenix", top_k=5)).passages == ()
    # Force a full rebuild (content sha unchanged, so use force path via config reindex).
    config = await kb.service.get_kb_config("kb1")
    await kb.service.reindex_with_config(kb_name="kb1", config=config, actor="user")
    assert len((await kb.service.search(kb_name="kb1", query="phoenix", top_k=5)).passages) == 1


async def test_concurrent_ingests_do_not_corrupt_index(kb) -> None:
    """Concurrent uploads into one KB serialize on the per-store lock; all
    succeed and keyword search sees every document (review finding H3)."""
    import asyncio

    await kb.create_kb("kb1")
    results = await asyncio.gather(
        *[
            _ingest(kb, "kb1", f"doc{i}.md", f"# Doc {i}\n\nuniqueword{i} shared".encode())
            for i in range(8)
        ],
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, errors[:3]
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 8
    res = await kb.service.search(kb_name="kb1", query="shared", top_k=20)
    assert len({p.document_id for p in res.passages}) == 8


async def test_reindex_reconstructs_documents_rows_after_db_loss(kb) -> None:
    """FR-008/SC-005: the documents table itself is rebuildable from the files.
    After total SQLite loss (documents rows included), reindex reconstructs the
    rows from each file's frontmatter — not just the chunk/FTS state."""
    from sqlalchemy import text

    await kb.create_kb("kb1")
    doc = await _ingest(kb, "kb1", "a.md", b"# A\n\nrebuildable banana")
    original_sha = doc.metadata["source_sha256"]

    async with kb.sm() as session:
        await session.execute(text("DELETE FROM documents_fts"))
        await session.execute(text("DELETE FROM chunks"))
        await session.execute(text("DELETE FROM documents"))
        await session.commit()

    stats = await kb.service.reindex(kb_name="kb1", actor="user")
    assert stats["reindexed"] == 1

    restored = await kb.documents.get_document("knowledge_base", "kb1", doc.id)
    assert restored is not None
    assert restored.source_mode == "converted"
    assert restored.title == "A"
    assert restored.metadata["source_sha256"] == original_sha
    res = await kb.service.search(kb_name="kb1", query="banana", top_k=5)
    assert len(res.passages) == 1


async def test_search_with_explicit_grep_mode_is_rejected(kb) -> None:
    """An explicit ``mode="grep"`` on search must 400 (the grep endpoint serves
    it), not be silently rewritten to keyword (review: unspecced silent rewrite)."""
    from coffer.domain.errors import SearchModeInvalid

    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\nsome text")
    with pytest.raises(SearchModeInvalid):
        await kb.service.search(kb_name="kb1", query="text", mode="grep")


async def test_search_with_disabled_mode_is_rejected(kb) -> None:
    """An explicit mode the KB has not enabled must 400, not silently fall back
    to the default (vector is the one flagged-fallback exception)."""
    from coffer.domain.errors import SearchModeInvalid

    await kb.create_kb("kb1", config={"enabled_modes": ["grep"], "default_mode": "grep"})
    await _ingest(kb, "kb1", "a.md", b"# A\n\nsome text")
    with pytest.raises(SearchModeInvalid):
        await kb.service.search(kb_name="kb1", query="text", mode="keyword")


async def test_search_default_grep_mode_serves_keyword(kb) -> None:
    """A store whose ``default_mode`` is grep still serves implicit searches
    (mapped to keyword) — only EXPLICIT grep requests are rejected."""
    await kb.create_kb("kb1", config={"enabled_modes": ["grep", "keyword"], "default_mode": "grep"})
    await _ingest(kb, "kb1", "a.md", b"# A\n\nsearchable text")
    result = await kb.service.search(kb_name="kb1", query="searchable")
    assert result.mode == "keyword"
    assert len(result.passages) == 1


async def test_list_documents_offset_past_total(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\nalpha")
    docs, total = await kb.service.list_documents(kb_name="kb1", limit=50, offset=10)
    assert docs == []
    assert total == 1


async def test_replace_reupload_audits_document_updated(kb) -> None:
    """FR-016: a changed replace re-upload of an existing filename is an UPDATE
    in the audit trail, not a second INGEST (and a byte-identical no-op re-upload
    audits nothing)."""
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# A\n\noriginal audited body")
    await _ingest(kb, "kb1", "a.md", b"# A\n\noriginal audited body")  # identical → no-op
    await _ingest(kb, "kb1", "a.md", b"# A\n\nchanged audited body", replace=True)

    events = await kb.audit.query(kind="knowledge_base", name="kb1", limit=50)
    types = [e.event_type for e in events]
    assert types.count("kb_document_ingested") == 1  # the no-op did not re-audit
    assert types.count("kb_document_updated") == 1


async def test_reindex_prunes_rows_whose_file_was_removed(kb) -> None:
    """FR-008 as a true mirror: a documents row whose docs/<id>.md vanished
    out-of-band is pruned (with its chunks) on reindex, reported in
    documents_removed (review: reindex was additive-only)."""
    await kb.create_kb("kb1")
    keep = await _ingest(kb, "kb1", "keep.md", b"# Keep\n\nkeeper body")
    gone = await _ingest(kb, "kb1", "gone.md", b"# Gone\n\nvanishing body")
    paths.doc_path("kb1", gone.id).unlink()

    stats = await kb.service.reindex(kb_name="kb1", actor="user")
    assert stats["removed"] == 1

    assert await kb.documents.get_document("knowledge_base", "kb1", gone.id) is None
    assert await kb.documents.get_document("knowledge_base", "kb1", keep.id) is not None
    assert (await kb.service.search(kb_name="kb1", query="vanishing", top_k=5)).passages == ()
