"""Concurrency: the reconcile/index pipeline under concurrent access.

The per-store lock + single-transaction ``upsert_chunks`` must keep concurrent
recalls/writes from interleaving their delete/insert batches (PK IntegrityError,
duplicated FTS rows) — review finding H3.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from coffer.domain.memory.scope import MemoryScope

pytestmark = pytest.mark.asyncio


async def test_concurrent_recalls_after_out_of_band_edit(mem) -> None:
    """24 concurrent recalls, each seeing the same sha delta, must all succeed
    and leave exactly one FTS row per chunk."""
    fact = await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="n",
        description="d",
        body="alpha beta gamma",
        actor="user",
    )
    _f, path = await mem.service.get_fact_with_path(store_name="global", fact_id=fact.id)
    p = Path(path)
    p.write_text(p.read_text().replace("alpha beta gamma", "delta epsilon zeta"))

    results = await asyncio.gather(
        *[mem.service.recall(cwd=None, query="delta", top_k=5) for _ in range(24)],
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, errors[:3]

    async with mem.documents._sm() as session:
        fts = (await session.execute(text("SELECT count(*) FROM documents_fts"))).scalar_one()
        chunks = (await session.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
    assert fts == chunks, (fts, chunks)


async def test_concurrent_writes_to_one_store(mem) -> None:
    """Concurrent fact writes to one store must not corrupt index state."""
    results = await asyncio.gather(
        *[
            mem.service.add_fact(
                scope=MemoryScope.GLOBAL,
                cwd=None,
                name=f"fact-{i}",
                description=f"desc {i}",
                body=f"unique fact body number {i}",
                actor="user",
            )
            for i in range(12)
        ],
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, errors[:3]
    _facts, total = await mem.service.list_facts(store_name="global")
    assert total == 12
