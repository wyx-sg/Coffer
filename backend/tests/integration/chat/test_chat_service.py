"""ChatService behaviour (spec 008-builtin-agent-chat)."""

from __future__ import annotations

import pytest

from coffer.application.builtin_agent.kind import (
    DEFAULT_BUILTIN_MODEL,
    DEFAULT_CONFIRM_TOOLS,
    ensure_default_builtin_agent,
)
from coffer.application.chat.service import ChatService
from coffer.domain.chat.conversation import ConversationStatus, MessageRole, MessageStatus
from coffer.domain.chat.runtime import (
    ConfirmationRequest,
    DoneEvent,
    ErrorEvent,
    TextDelta,
    ToolCallStarted,
    ToolResultEvent,
)
from coffer.domain.errors import (
    ConversationBusy,
    ConversationNotFound,
    LlmNotConfigured,
)
from coffer.infrastructure.chat.persistence import (
    SqlAlchemyConversationRepo,
    SqlAlchemyMessageRepo,
)
from tests.integration.chat.fakes import FakeRuntime

SPEC = "008-builtin-agent-chat"


async def _drain(gen):
    return [ev async for ev in gen]


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="a built-in agent is seeded on first startup"
)
async def test_builtin_agent_seeded_on_first_startup(chat_env):
    builtins = await chat_env.resources.list(kind="builtin_agent")
    assert len(builtins) == 1
    seeded = builtins[0]
    assert seeded.name == "coffer"
    assert seeded.enabled is True
    assert seeded.config["model"] == DEFAULT_BUILTIN_MODEL
    assert seeded.config["confirm_tools"] == DEFAULT_CONFIRM_TOOLS
    # Idempotent: a second ensure is a no-op, still exactly one.
    assert await ensure_default_builtin_agent(chat_env.resources) is None
    assert len(await chat_env.resources.list(kind="builtin_agent")) == 1
    # Lifecycle was audited.
    events = await chat_env.audit.query(kind="builtin_agent", name="coffer")
    assert any(e.event_type == "resource_created" for e in events)


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="chat with the built-in agent streams a reply"
)
async def test_chat_with_builtin_streams_reply(chat_env):
    chat_env.factory.runtime = FakeRuntime([TextDelta(text="Hel"), TextDelta(text="lo")])
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    events = await _drain(await chat_env.chat.send(conv.id, "hi"))
    assert isinstance(events[-1], DoneEvent)
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello"
    msgs = await chat_env.chat.get_messages(conv.id)
    assert [(m.role, m.content, m.status) for m in msgs] == [
        (MessageRole.USER, "hi", MessageStatus.COMPLETE),
        (MessageRole.ASSISTANT, "Hello", MessageStatus.COMPLETE),
    ]


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="the built-in agent can call Coffer gateway tools"
)
async def test_builtin_agent_calls_gateway_tools(chat_env):
    chat_env.factory.runtime = FakeRuntime(
        [
            ToolCallStarted(id="t1", tool="coffer__list_mcp_servers", args={}),
            ToolResultEvent(id="t1", tool="coffer__list_mcp_servers", ok=True, summary="2 servers"),
            TextDelta(text="You have 2 servers."),
        ]
    )
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    events = await _drain(await chat_env.chat.send(conv.id, "list my servers"))
    tool_calls = [e for e in events if isinstance(e, ToolCallStarted)]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool.startswith("coffer__")
    assistant = (await chat_env.chat.get_messages(conv.id))[-1]
    assert assistant.tool_calls[0].tool == "coffer__list_mcp_servers"
    assert assistant.tool_calls[0].result_summary == "2 servers"
    assert "2 servers" in assistant.content


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="conversation and messages persist across daemon restarts",
)
async def test_conversation_persists_across_restart(chat_env):
    chat_env.factory.runtime = FakeRuntime([TextDelta(text="remembered")])
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    await _drain(await chat_env.chat.send(conv.id, "store this"))
    # Simulate a restart: brand-new service instances over the same database.
    restarted = ChatService(
        conversations=SqlAlchemyConversationRepo(chat_env.sm),
        messages=SqlAlchemyMessageRepo(chat_env.sm),
        resources=chat_env.resources,
        runtime_factory=chat_env.factory,
        audit=chat_env.audit,
    )
    again = await restarted.get_conversation(conv.id)
    assert again.id == conv.id
    msgs = await restarted.get_messages(conv.id)
    assert [m.content for m in msgs] == ["store this", "remembered"]


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="create / list / rename / archive / restore / delete a conversation",
)
async def test_conversation_crud(chat_env):
    a = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    b = await chat_env.chat.create_conversation(target_ref="agent:claude-code")
    c = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    assert {x.id for x in await chat_env.chat.list_conversations()} == {a.id, b.id, c.id}

    renamed = await chat_env.chat.rename(a.id, "Renamed")
    assert renamed.title == "Renamed"

    await chat_env.chat.archive(b.id)
    active = await chat_env.chat.list_conversations(status=ConversationStatus.ACTIVE)
    active_ids = {x.id for x in active}
    assert b.id not in active_ids
    archived = await chat_env.chat.list_conversations(status=ConversationStatus.ARCHIVED)
    assert [x.id for x in archived] == [b.id]
    await chat_env.chat.restore(b.id)
    assert (await chat_env.chat.get_conversation(b.id)).status is ConversationStatus.ACTIVE

    await chat_env.chat.delete(c.id)
    with pytest.raises(ConversationNotFound):
        await chat_env.chat.get_conversation(c.id)


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="send returns 503 when no LLM provider is configured"
)
async def test_send_raises_when_llm_not_configured(chat_env):
    chat_env.factory.raise_llm_not_configured = True
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    with pytest.raises(LlmNotConfigured):
        await chat_env.chat.send(conv.id, "hi")
    # Nothing persisted; read paths still work.
    assert await chat_env.chat.get_messages(conv.id) == []
    assert (await chat_env.chat.get_conversation(conv.id)).id == conv.id


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="concurrent send on a streaming conversation is rejected",
)
async def test_concurrent_send_rejected(chat_env):
    chat_env.factory.runtime = FakeRuntime([TextDelta(text="x")])
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    gen1 = await chat_env.chat.send(conv.id, "first")
    assert chat_env.chat.has_active_turn(conv.id)
    with pytest.raises(ConversationBusy):
        await chat_env.chat.send(conv.id, "second")
    await _drain(gen1)  # release the active turn
    assert not chat_env.chat.has_active_turn(conv.id)


@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="a streaming turn can be stopped")
async def test_streaming_turn_can_be_stopped(chat_env):
    chat_env.factory.runtime = FakeRuntime(
        [TextDelta(text="partial"), ConfirmationRequest(id="c1", tool="coffer__delete_x", args={})]
    )
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    gen = await chat_env.chat.send(conv.id, "do it")
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, ConfirmationRequest):
            await chat_env.chat.stop(conv.id)
    assert not any(isinstance(e, DoneEvent) for e in seen)
    assistant = (await chat_env.chat.get_messages(conv.id))[-1]
    assert assistant.status is MessageStatus.CANCELED
    assert assistant.content == "partial"


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="a new conversation gets an auto-generated title after the first exchange",
)
async def test_auto_title_after_first_exchange(chat_env):
    chat_env.factory.runtime = FakeRuntime([TextDelta(text="hi")])
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    assert conv.title == "New chat"
    await _drain(await chat_env.chat.send(conv.id, "hello world"))
    titled = await chat_env.chat.get_conversation(conv.id)
    assert titled.title == "Generated Title"
    assert len(chat_env.titler.calls) == 1


async def test_auto_title_falls_back_to_truncated_message(chat_env):
    chat_env.titler._title = None  # generator yields nothing -> fallback
    chat_env.factory.runtime = FakeRuntime([TextDelta(text="hi")])
    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    await _drain(await chat_env.chat.send(conv.id, "how do I rename a branch safely"))
    titled = await chat_env.chat.get_conversation(conv.id)
    assert titled.title == "how do I rename a branch safely"


async def test_empty_message_rejected(chat_env):
    from coffer.domain.errors import MessageRejected

    conv = await chat_env.chat.create_conversation(target_ref="builtin_agent:coffer")
    with pytest.raises(MessageRejected):
        await chat_env.chat.send(conv.id, "   ")
    assert await chat_env.chat.get_messages(conv.id) == []


async def test_runtime_error_marks_message_failed(chat_env):
    chat_env.factory.runtime = FakeRuntime(
        [ErrorEvent(code="UPSTREAM_UNAVAILABLE", message="claude not found")]
    )
    conv = await chat_env.chat.create_conversation(target_ref="agent:claude-code")
    events = await _drain(await chat_env.chat.send(conv.id, "hi"))
    assert any(isinstance(e, ErrorEvent) for e in events)
    assistant = (await chat_env.chat.get_messages(conv.id))[-1]
    assert assistant.status is MessageStatus.FAILED
    assert assistant.error == {"code": "UPSTREAM_UNAVAILABLE", "message": "claude not found"}


async def test_target_missing_after_agent_deleted(chat_env):
    from coffer.domain.errors import TargetAgentMissing
    from coffer.domain.resource import ResourceRef

    chat_env.factory.runtime = FakeRuntime([TextDelta(text="x")])
    conv = await chat_env.chat.create_conversation(target_ref="agent:claude-code")
    await chat_env.resources.delete(ResourceRef("agent", "claude-code"), actor="test")
    with pytest.raises(TargetAgentMissing):
        await chat_env.chat.send(conv.id, "hi")
