"""The memory layer's sync boundary (spec vault-sync ``## What syncs``).

Two claims, and the value of the pair is that they are opposite. A hide or a
pin is a **decision** and must reach the other machine; everything under
``~/.coffer/memory/`` is **derived** from the agents installed on this one and
must not, because the other machine's next aggregation pass would recompute it
away.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from coffer.application.memory.overrides import Override
from coffer.application.memory.sync_state import AREA, MemoryOverrideSyncState
from coffer.infrastructure.persistence.memory_overrides_repo import OverrideRepository
from coffer.infrastructure.persistence.models import Base
from coffer.infrastructure.sync.paths import mirrored_trees


async def _repo(path: pathlib.Path) -> tuple[OverrideRepository, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return OverrideRepository(async_sessionmaker(engine, expire_on_commit=False)), engine


@pytest.mark.acceptance(
    spec="vault-sync", scenario="memory overrides travel but the derived tree does not"
)
async def test_overrides_travel_and_the_derived_tree_does_not(tmp_path: pathlib.Path) -> None:
    here, here_engine = await _repo(tmp_path / "a.db")
    there, there_engine = await _repo(tmp_path / "b.db")

    # A fact key is built from an agent, a native file and an anchor within it,
    # so it holds characters a path cannot. Using one here is the point.
    hidden_key = "claude-code::~/.claude/memory/prefs.md#L12 — never right"
    pinned_key = "codex::tasks/auth.md#always"
    await here.set(Override(fact_key=hidden_key, hidden=True), actor="user")
    await here.set(Override(fact_key=pinned_key, pinned=True), actor="user")

    docs, owned = await MemoryOverrideSyncState(here).export_docs()
    assert owned == [AREA]
    assert {name for name, _doc in docs} != {""}, "a doc name must be path-safe"
    for name, _doc in docs:
        assert "/" not in name and " " not in name

    failures = await MemoryOverrideSyncState(there).import_docs(list(docs))
    assert failures == []

    landed = await there.all()
    assert landed[hidden_key].hidden is True
    assert landed[pinned_key].pinned is True

    # And taking one back on the far machine clears it here.
    removed = [name for name, doc in docs if doc["fact_key"] == hidden_key]
    await MemoryOverrideSyncState(there).delete_docs(removed)
    assert hidden_key not in await there.all()
    assert pinned_key in await there.all()

    # The derived tree is not mirrored: only knowledge and skills are.
    assert [subdir for subdir, _root in mirrored_trees()] == ["knowledge", "skills"]

    await here_engine.dispose()  # type: ignore[attr-defined]
    await there_engine.dispose()  # type: ignore[attr-defined]
