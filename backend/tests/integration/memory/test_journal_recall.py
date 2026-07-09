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


async def test_reconcile_on_append_indexes_immediately(mem) -> None:
    """With a reconciler wired, an appended journal entry lands in the index
    right away — recall-able WITHOUT a prior recall triggering reconcile. This
    closes the write-only-to-disk gap that left distilled journal unsearchable
    when agents never recalled the store."""
    j = JournalService(
        scope=mem.scope,
        store_dir=paths.memory_store_dir,
        audit=mem.audit,
        now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC),
        reconciler=mem.reconciler,
        embedding=mem.embedding_resolver,
    )
    await j.append(cwd=mem.project_cwd, body="provisioned the redis cache", actor="agent")
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    store = store_name_for(resolved)
    # No recall has run — the journal doc exists purely from reconcile-on-append.
    doc = await mem.documents.get_document("memory", store, "journal-2026-06-21")
    assert doc is not None
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="redis cache", top_k=5)
    assert any("redis cache" in h.text for h in hits)


async def test_append_without_reconciler_defers_to_recall(mem) -> None:
    """Back-compat: with no reconciler wired, append only writes the file; the
    journal doc appears on the next recall (reconcile-on-read), as before."""
    j = JournalService(
        scope=mem.scope,
        store_dir=paths.memory_store_dir,
        audit=mem.audit,
        now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC),
    )
    await j.append(cwd=mem.project_cwd, body="a deferred note", actor="agent")
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    store = store_name_for(resolved)
    assert await mem.documents.get_document("memory", store, "journal-2026-06-21") is None
    await mem.service.recall(cwd=mem.project_cwd, query="note", top_k=5)  # reconciles-on-read
    assert await mem.documents.get_document("memory", store, "journal-2026-06-21") is not None


async def test_reindex_sweep_indexes_journal_backlog(mem) -> None:
    """The startup sweep indexes journal written to disk but never reconciled —
    the live-vault backlog (a store whose journal grew while it wasn't recalled).
    """
    from coffer.surfaces.http.memory_wiring import reindex_all_memory_stores

    # Append with NO reconciler wired → write-only-to-disk, as distillation was
    # before reconcile-on-append.
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="unindexed backlog entry", actor="agent")
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    store = store_name_for(resolved)
    assert await mem.documents.get_document("memory", store, "journal-2026-06-21") is None

    await reindex_all_memory_stores(
        resources=mem.resources,
        reconciler=mem.reconciler,
        embedding_resolver=mem.embedding_resolver,
    )
    assert await mem.documents.get_document("memory", store, "journal-2026-06-21") is not None


async def test_memory_digest_surfaces_facts_and_journal(mem) -> None:
    """The SessionStart digest (FR-055) surfaces the project's recent journal +
    knowledge index so an agent starts with memory without calling recall."""
    from coffer.application.memory.session_context import assemble_memory_digest

    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="rolled back the payments migration", actor="agent")
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        title="Auth",
        description="how login works",
        body="the login flow uses the shared session service",
        actor="agent",
    )
    digest = await assemble_memory_digest(
        cwd=mem.project_cwd, memory=mem.service, journal=j, max_chars=10_000
    )
    assert "## Project memory (via Coffer)" in digest
    assert "payments migration" in digest  # recent journal line
    assert "- Auth" in digest  # knowledge title index (title only)


async def test_memory_digest_empty_outside_project(mem) -> None:
    from coffer.application.memory.session_context import assemble_memory_digest

    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    digest = await assemble_memory_digest(
        cwd="/not/a/project", memory=mem.service, journal=j, max_chars=10_000
    )
    assert digest == ""


async def test_journal_and_knowledge_lanes_are_distinguishable(mem) -> None:
    j = _journal(mem, now=lambda: datetime(2026, 6, 21, 9, tzinfo=UTC))
    await j.append(cwd=mem.project_cwd, body="episodic: shipped the search feature", actor="agent")
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        title="search",
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
        title="f",
        description="d",
        body="a single knowledge fact",
        actor="agent",
    )
    # recall reconciles, so the journal doc is now in the index alongside the fact.
    await mem.service.recall(cwd=mem.project_cwd, query="event", top_k=5)
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    store = store_name_for(resolved)
    assert await mem.service.fact_count(store_name=store) == 1
