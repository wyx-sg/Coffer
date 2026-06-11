"""Integration: sqlite-vec vector path + graceful degradation.

These tests run the real ``vec_chunks`` path only when sqlite-vec loads; when it
does not, they assert the index degrades (returns no vector hits) without
raising — the keyword/grep fallback is the caller's job.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.knowledge.vec_index import VecIndex


def _doc(doc_id: str, resource: str) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=doc_id,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name=resource,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title="T",
        content_sha256="x",
        source_mode="converted",
        created_at=now,
        updated_at=now,
    )


def _sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return False
    return VecIndex(":memory:", 3, kind="kb", resource_name="probe").available()


@pytest.mark.asyncio
async def test_vector_search_degrades_without_vec(substrate) -> None:
    """No VecIndex wired ⇒ vector_search returns [] (never raises)."""
    await substrate.repo.upsert_document(_doc("d1", "kb1"))
    idx = SqliteKnowledgeIndex(
        substrate.sm, kind=KIND_KNOWLEDGE_BASE, resource_name="kb1", vec=None
    )
    await idx.upsert_chunks("d1", ["alpha"], [[0.1, 0.2, 0.3]])
    assert await idx.vector_search("kb1", [0.1, 0.2, 0.3], top_k=5) == []


def _vec(substrate, resource: str, dimensions: int) -> VecIndex:
    return VecIndex(
        str(substrate.db_path),
        dimensions,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name=resource,
    )


def _index(substrate, resource: str, vec: VecIndex) -> SqliteKnowledgeIndex:
    return SqliteKnowledgeIndex(
        substrate.sm, kind=KIND_KNOWLEDGE_BASE, resource_name=resource, vec=vec
    )


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_vector_search_knn(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kb1"))
    await substrate.repo.upsert_document(_doc("d2", "kb1"))
    idx = _index(substrate, "kb1", _vec(substrate, "kb1", 3))
    await idx.upsert_chunks("d1", ["near"], [[1.0, 0.0, 0.0]])
    await idx.upsert_chunks("d2", ["far"], [[0.0, 1.0, 0.0]])
    hits = await idx.vector_search("kb1", [0.9, 0.1, 0.0], top_k=2)
    assert hits
    assert hits[0].document_id == "d1"


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_two_stores_with_different_dimensions_coexist(substrate) -> None:
    """A per-store vector table lets stores with DIFFERENT embedding widths live
    in the same DB without colliding (one global ``vec_chunks`` could not)."""
    await substrate.repo.upsert_document(_doc("d1", "small"))
    await substrate.repo.upsert_document(_doc("d2", "big"))
    small = _index(substrate, "small", _vec(substrate, "small", 3))
    big = _index(substrate, "big", _vec(substrate, "big", 5))

    await small.upsert_chunks("d1", ["s"], [[1.0, 0.0, 0.0]])
    await big.upsert_chunks("d2", ["b"], [[1.0, 0.0, 0.0, 0.0, 0.0]])

    small_hits = await small.vector_search("small", [1.0, 0.0, 0.0], top_k=5)
    big_hits = await big.vector_search("big", [1.0, 0.0, 0.0, 0.0, 0.0], top_k=5)
    assert {h.document_id for h in small_hits} == {"d1"}
    assert {h.document_id for h in big_hits} == {"d2"}


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_scoped_vector_search_no_cross_store_leak_and_honors_top_k(substrate) -> None:
    """A scoped KNN must only ever return its own store's chunks (no leak) and
    must honor top_k even when another store holds nearer vectors."""
    # Two same-width stores. ``other`` holds the vectors closest to the query.
    for did, res in [("a1", "kbA"), ("a2", "kbA"), ("b1", "kbB"), ("b2", "kbB")]:
        await substrate.repo.upsert_document(_doc(did, res))
    a = _index(substrate, "kbA", _vec(substrate, "kbA", 3))
    b = _index(substrate, "kbB", _vec(substrate, "kbB", 3))

    # kbB vectors are the nearest to the query [1,0,0]; kbA vectors are farther.
    await b.upsert_chunks("b1", ["b-near"], [[1.0, 0.0, 0.0]])
    await b.upsert_chunks("b2", ["b-near2"], [[0.99, 0.01, 0.0]])
    await a.upsert_chunks("a1", ["a-far"], [[0.0, 1.0, 0.0]])
    await a.upsert_chunks("a2", ["a-far2"], [[0.0, 0.9, 0.1]])

    # Searching kbA must NOT surface kbB's nearer vectors, and must return only
    # kbA chunks (no leak) — under the old shared table the KNN would pick kbB.
    a_hits = await a.vector_search("kbA", [1.0, 0.0, 0.0], top_k=5)
    assert a_hits, "scoped search under-retrieved (would be empty if KNN hit only kbB)"
    assert {h.document_id for h in a_hits} == {"a1", "a2"}

    # top_k is honored within the store.
    a_hits_1 = await a.vector_search("kbA", [1.0, 0.0, 0.0], top_k=1)
    assert len(a_hits_1) == 1


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_width_change_rebuilds_only_that_store(substrate) -> None:
    """Re-binding a store at a new width rebuilds ITS table (no constraint error)
    while a sibling store at a different width is untouched."""
    await substrate.repo.upsert_document(_doc("d1", "kb1"))
    await substrate.repo.upsert_document(_doc("o1", "other"))
    other = _index(substrate, "other", _vec(substrate, "other", 7))
    await other.upsert_chunks("o1", ["o"], [[0.0] * 7])

    idx3 = _index(substrate, "kb1", _vec(substrate, "kb1", 3))
    await idx3.upsert_chunks("d1", ["v3"], [[1.0, 0.0, 0.0]])
    assert await idx3.vector_search("kb1", [1.0, 0.0, 0.0], top_k=5)

    # Same store re-bound at width 4: the old width-3 table is rebuilt.
    idx4 = _index(substrate, "kb1", _vec(substrate, "kb1", 4))
    await idx4.upsert_chunks("d1", ["v4"], [[1.0, 0.0, 0.0, 0.0]])
    hits = await idx4.vector_search("kb1", [1.0, 0.0, 0.0, 0.0], top_k=5)
    assert {h.document_id for h in hits} == {"d1"}

    # The sibling store (width 7) is unaffected by the kb1 rebuild.
    assert await other.vector_search("other", [0.0] * 7, top_k=5)


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_maintenance_delete_without_dimensions_removes_vec_rows(substrate) -> None:
    """Delete paths run without knowing the store's embedding width (document /
    fact deletion passes ``dimensions=None``); a width-less VecIndex must still
    delete this store's rows instead of leaking them forever."""
    await substrate.repo.upsert_document(_doc("d1", "kb1"))
    idx3 = _index(substrate, "kb1", _vec(substrate, "kb1", 3))
    await idx3.upsert_chunks("d1", ["near"], [[1.0, 0.0, 0.0]])

    maint = VecIndex(str(substrate.db_path), None, kind=KIND_KNOWLEDGE_BASE, resource_name="kb1")
    await maint.delete(["d1:0"])

    assert await idx3.vector_search("kb1", [1.0, 0.0, 0.0], top_k=5) == []


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_delete_with_stale_width_does_not_destroy_table(substrate) -> None:
    """A delete must never drop-and-rebuild the table on width mismatch: deletes
    can run with a stale/absent width, and a rebuild would silently destroy every
    OTHER chunk's vectors."""
    await substrate.repo.upsert_document(_doc("d1", "kb1"))
    await substrate.repo.upsert_document(_doc("d2", "kb1"))
    idx3 = _index(substrate, "kb1", _vec(substrate, "kb1", 3))
    await idx3.upsert_chunks("d1", ["a"], [[1.0, 0.0, 0.0]])
    await idx3.upsert_chunks("d2", ["b"], [[0.0, 1.0, 0.0]])

    stale = _vec(substrate, "kb1", 8)
    await stale.delete(["d1:0"])

    hits = await idx3.vector_search("kb1", [0.0, 1.0, 0.0], top_k=5)
    assert {h.document_id for h in hits} == {"d2"}


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_drop_store_removes_only_that_stores_vectors(substrate) -> None:
    await substrate.repo.upsert_document(_doc("d1", "kbA"))
    await substrate.repo.upsert_document(_doc("d2", "kbB"))
    a = _index(substrate, "kbA", _vec(substrate, "kbA", 3))
    b = _index(substrate, "kbB", _vec(substrate, "kbB", 3))
    await a.upsert_chunks("d1", ["a"], [[1.0, 0.0, 0.0]])
    await b.upsert_chunks("d2", ["b"], [[1.0, 0.0, 0.0]])

    await a.drop_store()
    # kbA's vectors are gone; a fresh search rebuilds an empty table.
    assert await a.vector_search("kbA", [1.0, 0.0, 0.0], top_k=5) == []
    # kbB is untouched.
    assert {h.document_id for h in await b.vector_search("kbB", [1.0, 0.0, 0.0], top_k=5)} == {"d2"}
