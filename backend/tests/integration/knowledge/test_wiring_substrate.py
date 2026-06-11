"""Integration: the production composition-root substrate (``wiring.py``).

Verifies the production ``index_factory``'s delete paths reach the sqlite-vec
table even when the caller supplies no embedding width — document/fact deletion
and store cleanup run with ``dimensions=None``, and a factory that only attaches
the vec index when a width is given leaks vector rows forever (review H1).
"""

from __future__ import annotations

import sqlite3

import pytest

from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
)
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.infrastructure.knowledge.vec_index import VecIndex, _store_table_name
from coffer.surfaces.http.wiring import build_substrate


def _sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return False
    return VecIndex(":memory:", 3, kind="kb", resource_name="probe").available()


def _store(tmp_path) -> StoreRef:  # type: ignore[no-untyped-def]
    return StoreRef(
        kind=KIND_KNOWLEDGE_BASE,
        resource_name="kb1",
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        docs_dir=str(tmp_path),
    )


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_delete_chunks_without_dimensions_reaches_vec_rows(substrate, tmp_path) -> None:
    _documents, retrieval, _reindexer = build_substrate(substrate.sm)
    store = _store(tmp_path)

    write_index = retrieval.index_for(store, dimensions=3)
    await write_index.upsert_chunks("d1", ["x"], [[1.0, 0.0, 0.0]])

    # The deletion path (document delete / fact forget) knows no width.
    maintenance_index = retrieval.index_for(store, dimensions=None)
    await maintenance_index.delete_chunks("d1")

    probe = VecIndex(str(substrate.db_path), 3, kind=KIND_KNOWLEDGE_BASE, resource_name="kb1")
    assert await probe.knn([1.0, 0.0, 0.0], 5) == []


@pytest.mark.skipif(not _sqlite_vec_available(), reason="sqlite-vec not installed/loadable")
@pytest.mark.asyncio
async def test_drop_store_without_dimensions_drops_vec_table(substrate, tmp_path) -> None:
    _documents, retrieval, _reindexer = build_substrate(substrate.sm)
    store = _store(tmp_path)

    write_index = retrieval.index_for(store, dimensions=3)
    await write_index.upsert_chunks("d1", ["x"], [[1.0, 0.0, 0.0]])

    await retrieval.drop_store(store, dimensions=None)

    table = _store_table_name(KIND_KNOWLEDGE_BASE, "kb1")
    conn = sqlite3.connect(str(substrate.db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    finally:
        conn.close()
    assert row is None
