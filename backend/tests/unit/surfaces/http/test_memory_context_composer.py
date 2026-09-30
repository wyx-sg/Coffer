"""The closure a channel turn reads memory through (spec memory "Deliver to
channel turns through the system prompt").

``memory_context_composer`` is what the composition root hands every agent
provider as ``compose_memory_context``. It answers ``None`` — no memory header
at all — when there is nothing to deliver; otherwise it answers the composed
index, audited as the turn's ``session_start`` fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.memory.turn_retrieval import TurnRetrieval
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


@dataclass
class _Delivery:
    fired: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def record_fired(self, agent_uid: str, details: dict[str, Any] | None = None) -> None:
        self.fired.append((agent_uid, dict(details or {})))


class _Agents:
    async def list(self) -> list[Any]:
        return [SimpleNamespace(uid="u-claude", config={"type": "claude_code"})]


def _composer(memory: _FakeMemory, delivery: _Delivery | None = None) -> Any:
    turns = TurnRetrieval(
        None,  # type: ignore[arg-type]  # the index never ranks a prompt
        delivery or _Delivery(),
        _Agents(),  # type: ignore[arg-type]
        memory,
    )
    return memory_context_composer(turns)


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
    delivery = _Delivery()
    compose = _composer(_FakeMemory([]), delivery)
    assert await compose("claude_code", "/home/dev/coffer", "c1") is None
    assert delivery.fired == []


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a channel turn carries the index without a hook")
async def test_notes_answer_the_composed_index() -> None:
    delivery = _Delivery()
    compose = _composer(_FakeMemory([_note()]), delivery)
    text = await compose("claude_code", "/home/dev/coffer", "c1")
    assert text is not None
    assert "Two spaces are not a tab." in text
    assert [(uid, d["moment"]) for uid, d in delivery.fired] == [("u-claude", "session_start")]


@pytest.mark.asyncio
async def test_unreadable_tree_costs_the_turn_its_index_not_its_reply() -> None:
    compose = _composer(_BrokenMemory([_note()]))
    assert await compose("codex", "/home/dev/coffer", "c1") is None
