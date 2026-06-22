"""Integration: MemoryService lane read methods (Slice 7 four-lane UI).

Pure reads over the real substrate — journal / handoff / consolidation-log
lanes. Populated store → ordered entries; empty store → empty/None, never an
error. The HTTP routes (test_lane_routes.py) wrap the same reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.application.memory import lane_reads
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    handoff_path,
    journal_path,
)
from coffer.infrastructure.memory.handoff_files import write_handoff
from coffer.infrastructure.memory.journal_files import append_entry

pytestmark = pytest.mark.asyncio


async def _global_store_dir(mem) -> Path:
    """Provision the global store and return its on-disk dir."""
    await mem.service.ensure_store(GLOBAL_STORE_NAME)
    return (await mem.service.resolved_store(GLOBAL_STORE_NAME)).store_dir


# --- journal ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="journal lane entries are readable for a store",
)
async def test_read_journal_newest_period_first(mem) -> None:
    store_dir = await _global_store_dir(mem)
    append_entry(
        journal_path(store_dir, "2026-05"),
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        body="May event",
    )
    append_entry(
        journal_path(store_dir, "2026-06"),
        timestamp=datetime(2026, 6, 1, tzinfo=UTC),
        body="June event",
    )

    files = await lane_reads.journal_for_store(GLOBAL_STORE_NAME, mem.service.resolved_store)

    assert [f.period for f in files] == ["2026-06", "2026-05"]
    assert "June event" in files[0].text
    assert files[0].path == str(journal_path(store_dir, "2026-06"))
    assert files[0].folder_path == str(journal_path(store_dir, "2026-06").parent)


async def test_read_journal_empty_store(mem) -> None:
    await _global_store_dir(mem)
    assert await lane_reads.journal_for_store(GLOBAL_STORE_NAME, mem.service.resolved_store) == []


# --- handoff ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="handoff scenes are listed per branch for a store",
)
async def test_read_handoff_scenes_per_branch(mem) -> None:
    store_dir = await _global_store_dir(mem)
    write_handoff(
        handoff_path(store_dir, "feature-a"),
        branch="feature/a",
        body="WIP on feature a",
        updated_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )
    write_handoff(
        handoff_path(store_dir, "main"),
        branch="main",
        body="clean tree",
        updated_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
    )

    scenes = await lane_reads.handoff_for_store(GLOBAL_STORE_NAME, mem.service.resolved_store)

    by_branch = {s.branch: s for s in scenes}
    assert set(by_branch) == {"feature/a", "main"}
    assert by_branch["feature/a"].text == "WIP on feature a"
    assert by_branch["main"].updated_at == datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    assert by_branch["main"].path == str(handoff_path(store_dir, "main"))
    assert by_branch["main"].folder_path == str(handoff_path(store_dir, "main").parent)


async def test_read_handoff_empty_store(mem) -> None:
    await _global_store_dir(mem)
    assert await lane_reads.handoff_for_store(GLOBAL_STORE_NAME, mem.service.resolved_store) == []


# --- consolidation log ------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="the consolidation changelog is readable for a store",
)
async def test_read_consolidation_log_present(mem) -> None:
    store_dir = await _global_store_dir(mem)
    store_dir.mkdir(parents=True, exist_ok=True)
    changelog = consolidation_log_path(store_dir)
    changelog.write_text("# Consolidation log\n\n- drained 3 items\n", encoding="utf-8")

    log = await lane_reads.consolidation_log_for_store(
        GLOBAL_STORE_NAME, mem.service.resolved_store
    )

    assert log.text is not None
    assert "drained 3 items" in log.text
    assert log.path == str(changelog)
    assert log.folder_path == str(changelog.parent)


async def test_read_consolidation_log_absent(mem) -> None:
    store_dir = await _global_store_dir(mem)
    log = await lane_reads.consolidation_log_for_store(
        GLOBAL_STORE_NAME, mem.service.resolved_store
    )
    assert log.text is None
    assert log.path == str(consolidation_log_path(store_dir))
    assert log.folder_path == str(store_dir)
