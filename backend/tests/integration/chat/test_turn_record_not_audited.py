"""A turn leaves no audit-log row, and Coffer keeps no copy of it (spec chat "Keep a
turn's record in its conversation, not the audit log" — the record is now the
agent's own session).

Runs a real turn through the orchestrator against the real SQLite conversation
repository on a database that also carries the audit table, then reads back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnStarted,
)
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import AuditLogModel
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import FakeAgentAdapter, FakeAgentProvider

pytestmark = pytest.mark.asyncio


@pytest.mark.acceptance(
    spec="chat", scenario="a turn is recorded in its conversation and not in the audit log"
)
async def test_a_turn_is_not_recorded_in_the_audit_log_or_kept_as_text(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    try:
        adapter = FakeAgentAdapter(
            [
                TurnStarted(),
                TextDelta(text="Checking. "),
                ToolCall(tool_use_id="t1", tool_name="read_file", tool_input={"path": "/a"}),
                ToolResult(
                    tool_use_id="t1", tool_name="read_file", output={"text": "x"}, error=None
                ),
                TextDelta(text="Done."),
                TurnDone(prompt_tokens=12, completion_tokens=4, stop_reason="end_turn"),
            ],
            model_id="model-x",
        )
        registry = AgentProviderRegistry()
        registry.register(FakeAgentProvider(adapter, agent_key="agent"), display_name="Agent")
        chat = ChatService(conversations=ConversationRepo(sm), registry=registry)
        orchestrator = TurnOrchestrator(chat_service=chat, registry=registry)

        conv = await chat.create_conversation(
            agent_key="agent", channel_uid="chan", peer_chat_id="peer"
        )
        queue = await start_turn(orchestrator, conv.id, "read /a")
        while await queue.get() is not None:
            pass

        # The index row is named and bumped; the text itself is nowhere in Coffer.
        row = await chat.get_conversation(conv.id)
        assert row.title == "read /a"
        assert row.updated_at > conv.updated_at
        async with sm() as session:
            tables = {
                r[0]
                for r in await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            }
            audit_rows = (
                await session.execute(text(f"SELECT COUNT(*) FROM {AuditLogModel.__tablename__}"))
            ).scalar_one()
        assert "chat_messages" not in tables
        assert audit_rows == 0
    finally:
        await engine.dispose()
