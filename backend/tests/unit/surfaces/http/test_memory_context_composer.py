"""The closure a channel turn reads memory through (spec memory "Deliver to
channel turns through the system prompt").

``memory_context_composer`` is what the composition root hands every agent
provider as ``compose_memory_context``. It answers ``None`` — no memory header
at all — when there is nothing to deliver; otherwise it answers the composed
index.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from coffer.domain.memory.note import TYPE_USER, Note, Origin
from coffer.surfaces.http.memory_turn_wiring import memory_context_composer


@dataclass(frozen=True)
class _Partition:
    name: str
    repository_path: str


class _FakeMemory:
    def __init__(self, notes: list[Note]) -> None:
        self._notes = notes

    async def served_partitions(self) -> list[str]:
        return ["global"]

    async def list_notes(self, partition: str) -> list[Note]:
        return [n for n in self._notes if n.partition == partition]

    async def list_partitions(self) -> list[_Partition]:
        return [_Partition("global", "")]


class _BrokenMemory(_FakeMemory):
    async def list_partitions(self) -> list[_Partition]:
        raise OSError("tree unreadable")


def _note() -> Note:
    return Note(
        slug="likes-tabs",
        title="Likes tabs",
        description="Two spaces are not a tab.",
        type=TYPE_USER,
        body="body",
        partition="global",
        origins=(Origin(agent="codex", native_path="/n/likes-tabs.md", anchor="a"),),
        created_at="2026-01-01",
        updated_at="2026-01-01",
    )


@pytest.mark.asyncio
async def test_nothing_to_deliver_appends_nothing() -> None:
    compose = memory_context_composer(_FakeMemory([]))
    assert await compose("claude_code", "/home/dev/coffer") is None


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a channel turn carries the index without a hook")
async def test_notes_answer_the_composed_index() -> None:
    compose = memory_context_composer(_FakeMemory([_note()]))
    text = await compose("claude_code", "/home/dev/coffer")
    assert text is not None
    assert "Two spaces are not a tab." in text


@pytest.mark.asyncio
async def test_unreadable_tree_costs_the_turn_its_index_not_its_reply() -> None:
    compose = memory_context_composer(_BrokenMemory([_note()]))
    assert await compose("codex", "/home/dev/coffer") is None
