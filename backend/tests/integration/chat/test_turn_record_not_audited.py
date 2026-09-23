"""A turn's record is its conversation — never the audit log (spec chat "Keep a
turn's record in its conversation, not the audit log").

Runs a real turn through the orchestrator against real SQLite repositories on a
database that also carries the audit table, then reads both back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnStarted,
)
from coffer.domain.chat.message import Role, TextBlock, ToolResultBlock, ToolUseBlock
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import AuditLogModel
from tests.unit.chat.conftest import FakeAgentAdapter, FakeAgentProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_turns()
    yield
    clear_active_turns()


@pytest.mark.acceptance(
    spec="chat", scenario="a turn is recorded in its conversation and not in the audit log"
)
async def test_a_turn_is_recorded_in_its_conversation_and_not_in_the_audit_log(tmp_path) -> None:  # type: ignore[no-untyped-def]
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
        chat = ChatService(
            conversations=ConversationRepo(sm), messages=MessageRepo(sm), registry=registry
        )
        orchestrator = TurnOrchestrator(chat_service=chat, registry=registry)

        conv = await chat.create_conversation(agent_key="agent")
        queue = await orchestrator.start_turn(conv.id, "read /a")
        while await queue.get() is not None:
            pass

        messages = await chat.list_messages(conv.id)
        assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT]
        reply = messages[1]
        assert reply.status == "complete"
        assert reply.model_id == "model-x"
        assert (reply.prompt_tokens, reply.completion_tokens) == (12, 4)
        kinds = [type(b) for b in reply.content]
        assert ToolUseBlock in kinds and ToolResultBlock in kinds and TextBlock in kinds
        tool_use = next(b for b in reply.content if isinstance(b, ToolUseBlock))
        assert tool_use.tool_name == "read_file"

        async with sm() as session:
            audit_rows = (
                await session.execute(text(f"SELECT COUNT(*) FROM {AuditLogModel.__tablename__}"))
            ).scalar_one()
        assert audit_rows == 0
    finally:
        await engine.dispose()
