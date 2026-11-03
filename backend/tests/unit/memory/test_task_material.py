"""Which memories an agent filed as task material (spec memory "Flag the
memories an agent filed as task material"), and the reminder they raise."""

from __future__ import annotations

import pytest

from coffer.application.memory.attention import TO_SORT_THRESHOLD, MemoryAttentionSource
from coffer.domain.memory.hub import (
    CLAUDE_CODE,
    CODEX,
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    TYPE_REFERENCE,
    TYPE_USER,
    HubEntry,
    Origin,
)
from coffer.infrastructure.memory.task_material import is_task_material


def _entry(agent: str, source: str = "x.md", type_: str = TYPE_USER) -> HubEntry:
    return HubEntry(
        id="0123456789abcdef",
        origin=Origin(machine="m", agent=agent, source=source),
        project="",
        type=type_,
        title="t",
        description="d",
        body="b",
        created_at="",
        updated_at="",
    )


@pytest.mark.acceptance(spec="memory", scenario="task material is flagged from where it was filed")
def test_task_material_is_read_from_where_the_agent_filed_it() -> None:
    assert is_task_material(_entry(CODEX, "memories/MEMORY.md::IA sheet::Reusable knowledge::1"))
    assert not is_task_material(_entry(CODEX, "memories/memory_summary.md::profile::user-profile"))
    assert not is_task_material(
        _entry(CODEX, "memories/memory_summary.md::profile::User preferences::1")
    )
    assert is_task_material(_entry(CLAUDE_CODE, type_=TYPE_REFERENCE))
    for type_ in (TYPE_USER, TYPE_FEEDBACK, TYPE_PROJECT):
        assert not is_task_material(_entry(CLAUDE_CODE, type_=type_))


@pytest.mark.acceptance(spec="memory", scenario="the reminder waits for enough task notes")
async def test_the_reminder_waits_for_enough_memories() -> None:
    async def few() -> int:
        return TO_SORT_THRESHOLD - 1

    async def enough() -> int:
        return TO_SORT_THRESHOLD

    assert await MemoryAttentionSource(few).items() == []
    (item,) = await MemoryAttentionSource(enough).items()
    assert item.reason_code == "memory_to_sort"
    assert item.action.path == "/api/v1/memory/sync/to-sort"
