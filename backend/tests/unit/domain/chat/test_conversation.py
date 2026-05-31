"""Conversation / Message domain value objects."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.chat.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageStatus,
    ToolCall,
)
from coffer.domain.resource import ResourceRef


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=UTC)


def test_conversation_target_parses_to_resource_ref():
    c = Conversation(
        id="c1",
        target_ref="builtin_agent:coffer",
        title="New chat",
        status=ConversationStatus.ACTIVE,
        model_snapshot={"model": "anthropic:claude-sonnet-4-6"},
        created_at=_now(),
        updated_at=_now(),
    )
    assert c.target == ResourceRef("builtin_agent", "coffer")
    assert c.is_active is True


def test_conversation_target_supports_external_agent():
    c = Conversation(
        id="c2",
        target_ref="agent:claude-code",
        title=None,
        status=ConversationStatus.ARCHIVED,
        model_snapshot={},
        created_at=_now(),
        updated_at=_now(),
    )
    assert c.target == ResourceRef("agent", "claude-code")
    assert c.is_active is False


def test_message_defaults_have_no_tool_calls_or_error():
    m = Message(
        id="m1",
        conversation_id="c1",
        role=MessageRole.USER,
        content="hello",
        status=MessageStatus.COMPLETE,
        created_at=_now(),
    )
    assert m.tool_calls == []
    assert m.error is None


def test_tool_call_records_confirmation_state():
    tc = ToolCall(id="t1", tool="coffer__delete_memory", args_summary="{id: 5}")
    assert tc.result_summary is None
    assert tc.confirmed is None
    confirmed = ToolCall(
        id="t2", tool="coffer__add_memory", args_summary="{}", result_summary="ok", confirmed=True
    )
    assert confirmed.confirmed is True


def test_status_enum_values_are_wire_stable():
    assert ConversationStatus.ACTIVE.value == "active"
    assert ConversationStatus.ARCHIVED.value == "archived"
    assert {s.value for s in MessageStatus} == {"streaming", "complete", "failed", "canceled"}
    assert {r.value for r in MessageRole} == {"user", "assistant", "tool"}
