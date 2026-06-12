"""Unit tests for ChatService using in-memory fake repos + a fake agent provider."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.service import ChatService
from coffer.domain.chat.message import Role, TextBlock, ToolUseBlock
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound, UnknownAgent

from .conftest import (
    FakeAgentProvider,
    FakeAuditRepo,
    FakeConversationRepo,
    FakeMessageRepo,
    make_registry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_service() -> tuple[
    ChatService, FakeConversationRepo, FakeMessageRepo, FakeAuditRepo, FakeAgentProvider
]:
    conv_repo = FakeConversationRepo()
    msg_repo = FakeMessageRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    registry, provider = make_registry(adapter=None)
    svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )
    return svc, conv_repo, msg_repo, audit_repo, provider


# ---------------------------------------------------------------------------
# Conversation creation + the agent-provider seam
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_conversation_returns_placeholder_title() -> None:
    svc, _conv_repo, _, _audit_repo, _ = make_service()
    conv = await svc.create_conversation()
    assert conv.title == "New conversation"
    assert conv.agent_key == "builtin"
    assert conv.model_id is None


@pytest.mark.asyncio
async def test_create_conversation_emits_audit_event() -> None:
    svc, _, _, audit_repo, _ = make_service()
    conv = await svc.create_conversation(actor="alice")
    entry = next(e for e in audit_repo.entries if e.event_type == "conversation_created")
    assert entry.details["conversation_id"] == conv.id
    assert entry.actor == "alice"


@pytest.mark.asyncio
async def test_create_conversation_calls_provider_init_conversation() -> None:
    svc, _, _, _, provider = make_service()
    conv = await svc.create_conversation(agent_config={"model_id": "m-1"})
    assert provider.init_calls == [(conv.id, {"model_id": "m-1"})]


@pytest.mark.asyncio
async def test_create_conversation_unknown_agent_raises_and_persists_nothing() -> None:
    svc, conv_repo, _, _, _ = make_service()
    with pytest.raises(UnknownAgent):
        await svc.create_conversation(agent_key="no-such-agent")
    assert await conv_repo.list() == []


@pytest.mark.asyncio
async def test_create_conversation_rolls_back_when_init_rejects_config() -> None:
    conv_repo = FakeConversationRepo()
    msg_repo = FakeMessageRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    provider = FakeAgentProvider(
        adapter=None,
        init_error=AgentConfigRejected(reason="model_not_found", message="no such model"),
    )
    registry, _ = make_registry(provider=provider)
    svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )

    with pytest.raises(AgentConfigRejected):
        await svc.create_conversation(agent_config={"model_id": "ghost"})

    # The conversation row was rolled back — nothing left half-created.
    assert await conv_repo.list() == []
    assert not any(e.event_type == "conversation_created" for e in audit_repo.entries)


# ---------------------------------------------------------------------------
# Conversation read / rename / model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_raises_not_found() -> None:
    svc, _, _, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.get_conversation("missing-id")


@pytest.mark.asyncio
async def test_list_conversations_newest_first() -> None:
    svc, conv_repo, _msg_repo, _, _ = make_service()
    c1 = await svc.create_conversation()
    c2 = await svc.create_conversation()
    await conv_repo.touch(c1.id, datetime(2030, 1, 2, tzinfo=UTC))
    await conv_repo.touch(c2.id, datetime(2030, 1, 1, tzinfo=UTC))
    result = await svc.list_conversations()
    assert result[0].id == c1.id


@pytest.mark.asyncio
async def test_rename_conversation() -> None:
    svc, _, _, _, _ = make_service()
    conv = await svc.create_conversation()
    updated = await svc.rename_conversation(conv.id, new_title="My Chat")
    assert updated.title == "My Chat"


@pytest.mark.asyncio
async def test_rename_conversation_not_found() -> None:
    svc, _, _, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.rename_conversation("bad-id", new_title="Title")


@pytest.mark.asyncio
async def test_set_conversation_model_then_clear() -> None:
    svc, _, _, _, _ = make_service()
    conv = await svc.create_conversation()
    updated = await svc.set_conversation_model(conv.id, model_id="m-001")
    assert updated.model_id == "m-001"
    cleared = await svc.set_conversation_model(conv.id, model_id=None)
    assert cleared.model_id is None


# ---------------------------------------------------------------------------
# Conversation deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_conversation_removes_messages() -> None:
    svc, conv_repo, msg_repo, _audit_repo, _ = make_service()
    conv = await svc.create_conversation()
    await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="hi")])
    await svc.delete_conversation(conv.id)

    assert await conv_repo.get(conv.id) is None
    assert await msg_repo.list_by_conversation(conv.id) == []


@pytest.mark.asyncio
async def test_delete_conversation_emits_audit_event() -> None:
    svc, _, _, audit_repo, _ = make_service()
    conv = await svc.create_conversation()
    await svc.delete_conversation(conv.id, actor="bob")
    assert any(e.event_type == "conversation_deleted" for e in audit_repo.entries)


@pytest.mark.asyncio
async def test_delete_conversation_calls_provider_on_conversation_deleted() -> None:
    svc, _, _, _, provider = make_service()
    conv = await svc.create_conversation()
    await svc.delete_conversation(conv.id)
    assert provider.deleted == [conv.id]


@pytest.mark.asyncio
async def test_delete_conversation_not_found() -> None:
    svc, _, _, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.delete_conversation("no-such-id")


@pytest.mark.asyncio
async def test_delete_conversation_calls_cancel_fn() -> None:
    svc, _, _, _, _ = make_service()
    conv = await svc.create_conversation()
    cancelled: list[str] = []
    await svc.delete_conversation(conv.id, cancel_turn_fn=lambda cid: cancelled.append(cid))
    assert conv.id in cancelled


# ---------------------------------------------------------------------------
# Message operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_message_basic() -> None:
    svc, _, _msg_repo, _, _ = make_service()
    conv = await svc.create_conversation()
    msg = await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="hello")])
    assert msg.role == Role.USER
    assert msg.seq == 0
    assert msg.status == "complete"


@pytest.mark.asyncio
async def test_first_user_message_sets_title() -> None:
    svc, conv_repo, _, _, _ = make_service()
    conv = await svc.create_conversation()
    await svc.append_message(
        conv.id, role=Role.USER, content=[TextBlock(text="Tell me about Python")]
    )
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "Tell me about Python"


@pytest.mark.asyncio
async def test_first_user_message_title_truncated_at_60_chars() -> None:
    svc, conv_repo, _, _, _ = make_service()
    conv = await svc.create_conversation()
    await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="A" * 100)])
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert len(updated.title) == 60


@pytest.mark.asyncio
async def test_second_user_message_does_not_change_title() -> None:
    svc, conv_repo, _, _, _ = make_service()
    conv = await svc.create_conversation()
    await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="First message")])
    await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="Second message")])
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "First message"


@pytest.mark.asyncio
async def test_append_message_increments_seq() -> None:
    svc, _, _msg_repo, _, _ = make_service()
    conv = await svc.create_conversation()
    m0 = await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="q")])
    m1 = await svc.append_message(
        conv.id, role=Role.ASSISTANT, content=[TextBlock(text="a")], status="complete"
    )
    assert m0.seq == 0
    assert m1.seq == 1


@pytest.mark.asyncio
async def test_list_messages_ordered_by_seq() -> None:
    svc, _, _, _, _ = make_service()
    conv = await svc.create_conversation()
    await svc.append_message(conv.id, role=Role.USER, content=[TextBlock(text="q")])
    await svc.append_message(conv.id, role=Role.ASSISTANT, content=[TextBlock(text="a")])
    msgs = await svc.list_messages(conv.id)
    assert [m.seq for m in msgs] == [0, 1]


@pytest.mark.asyncio
async def test_list_messages_conversation_not_found() -> None:
    svc, _, _, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.list_messages("no-such-id")


@pytest.mark.asyncio
async def test_append_with_non_text_content() -> None:
    svc, _, _msg_repo, _, _ = make_service()
    conv = await svc.create_conversation()
    tool_use = ToolUseBlock(tool_use_id="t1", tool_name="coffer__list_skills", tool_input={})
    msg = await svc.append_message(
        conv.id, role=Role.ASSISTANT, content=[tool_use], status="complete"
    )
    assert msg.content[0] == tool_use
