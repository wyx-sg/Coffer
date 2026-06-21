"""Integration: the journal lane participates in recall (FR-043/044).

A journal entry written via ``JournalService.append`` becomes searchable by
keyword AND grep, is tagged as the journal lane in ``source``, and does NOT
inflate a store's ``fact_count`` (which counts only the knowledge lane).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.memory.journal import JournalService
from coffer.application.memory.stores import store_name_for
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.knowledge import paths

pytestmark = pytest.mark.asyncio


def _journal(mem, *, now):  # type: ignore[no-untyped-def]
    return JournalService(
        scope=mem.scope, store_dir=paths.memory_store_dir, audit=mem.audit, now=now
    )


async def test_journal_entry_is_recalled_by_keyword(mem) -> None:
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(
        cwd=mem.project_cwd,
        body="deployed the auth service to the staging cluster",
        actor="agent",
    )
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="auth service staging", top_k=5)
    assert any("auth service" in h.text for h in hits)
    assert any("/journal/" in h.source for h in hits), [h.source for h in hits]


async def test_journal_entry_is_recalled_by_grep(mem) -> None:
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="rolled back the payments migration", actor="agent")
    hits, _fb = await mem.service.recall(
        cwd=mem.project_cwd, query="payments migration", top_k=5, mode="grep"
    )
    assert any("payments migration" in h.text for h in hits)
    assert any("/journal/" in h.source for h in hits), [h.source for h in hits]


async def test_journal_recall_reflects_a_later_append(mem) -> None:
    # Lazy reindex-on-read: a second append is searchable on the next recall.
    times = iter([datetime(2026, 6, 21, 9, tzinfo=UTC), datetime(2026, 6, 21, 10, tzinfo=UTC)])
    j = JournalService(
        scope=mem.scope, store_dir=paths.memory_store_dir, audit=mem.audit, now=lambda: next(times)
    )
    await j.append(cwd=mem.project_cwd, body="first episodic note about widgets", actor="agent")
    await mem.service.recall(cwd=mem.project_cwd, query="widgets", top_k=5)
    await j.append(cwd=mem.project_cwd, body="second episodic note about gadgets", actor="agent")
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="gadgets", top_k=5)
    assert any("gadgets" in h.text for h in hits), [h.text for h in hits]


async def test_journal_and_knowledge_lanes_are_distinguishable(mem) -> None:
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="episodic: shipped the search feature", actor="agent")
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="search",
        description="search facts",
        body="the search feature uses the shared retrieval engine",
        actor="agent",
    )
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="search feature", top_k=10)
    sources = [h.source for h in hits]
    assert any("/journal/" in s for s in sources), sources
    assert any("/knowledge/" in s for s in sources), sources


async def test_journal_is_not_counted_in_fact_count(mem) -> None:
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="an episodic event", actor="agent")
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="f",
        description="d",
        body="a single knowledge fact",
        actor="agent",
    )
    # recall reconciles, so the journal doc is now in the index alongside the fact.
    await mem.service.recall(cwd=mem.project_cwd, query="event", top_k=5)
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    store = store_name_for(resolved)
    assert await mem.service.fact_count(store_name=store) == 1
