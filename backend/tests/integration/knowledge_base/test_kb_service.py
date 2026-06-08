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


async def test_ingest_dedup_blocks_without_replace(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# Hello\n\nworld")
    with pytest.raises(IngestRejected) as exc:
        await _ingest(kb, "kb1", "a.md", b"# Hello\n\nworld")
    assert exc.value.reason == "duplicate"
    # replace=true succeeds.
    await _ingest(kb, "kb1", "a.md", b"# Hello\n\nworld", replace=True)


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


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="grep returns file/line matches")
async def test_grep_returns_hits(kb) -> None:
    await kb.create_kb("kb1")
    await _ingest(kb, "kb1", "a.md", b"# Make\n\nthe make release target ships it")
    hits = await kb.service.grep(kb_name="kb1", pattern="make release")
    assert len(hits) >= 1
    assert any("make release" in h.line for h in hits)
    assert all(h.line_number >= 1 for h in hits)


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
