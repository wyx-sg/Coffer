"""A daemon that dies mid-turn keeps what was streamed (spec chat "Keep partial
output when a turn is interrupted or fails", "Sweep streaming rows left by a
crashed daemon").

Real SQLite: a turn streams text, a partial flush lands on the ``streaming``
row, then the process "dies" — nothing finalises the row. A fresh store over
the same database file runs the startup sweep and reads the row back: the
streamed text is there and the row is ``failed``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from coffer.application.chat import turn_persistence
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    active_turns,
    clear_active_turns,
)
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnStarted
from coffer.domain.chat.message import Role, TextBlock
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from tests.unit.chat.conftest import FakeAgentProvider


@pytest.fixture(autouse=True)
def _clean() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


class _StreamThenHang:
    model_id = None

    def __init__(self, clock: list[float]) -> None:
        self._clock = clock
        self.streamed = asyncio.Event()

    async def run_turn(self, *, history: Any, **_: object) -> AsyncIterator[AgentEvent]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="streamed before ")
        self._clock[0] += 5.0  # the flush interval passes before the next token
        yield TextDelta(text="the crash")
        self.streamed.set()
        await asyncio.Event().wait()


async def test_a_crash_keeps_the_flushed_partial_for_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(turn_persistence, "_clock", lambda: clock[0])
    url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    engine = create_async_engine_with_pragmas(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    adapter = _StreamThenHang(clock)
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(adapter), display_name="Coffer Assistant")
    chat = ChatService(
        conversations=ConversationRepo(sm), messages=MessageRepo(sm), registry=registry
    )
    orchestrator = TurnOrchestrator(chat_service=chat, registry=registry)
    orchestrator._flush_interval = 1.0

    fresh_engine = create_async_engine_with_pragmas(url)
    try:
        conv = await chat.create_conversation(agent_key="builtin")
        await orchestrator.start_turn(conv.id, "hi")
        await asyncio.wait_for(adapter.streamed.wait(), timeout=5.0)
        await asyncio.sleep(0.05)  # let the flush's write commit

        # The "crash": the running daemon never finalises. A new process opens
        # the same database and runs its startup sweep.
        fresh = MessageRepo(session_maker(fresh_engine))
        assert await TurnOrchestrator.sweep_streaming_messages(fresh) == 1
        rows = [m for m in await fresh.list_by_conversation(conv.id) if m.role is Role.ASSISTANT]
        assert len(rows) == 1
        assert rows[0].status == "failed"
        text = "".join(b.text for b in rows[0].content if isinstance(b, TextBlock))
        assert text == "streamed before the crash"
    finally:
        task = active_turns().get(conv.id)
        if task is not None and task.task is not None:
            task.task.cancel()
            await asyncio.gather(task.task, return_exceptions=True)
        await fresh_engine.dispose()
        await engine.dispose()
