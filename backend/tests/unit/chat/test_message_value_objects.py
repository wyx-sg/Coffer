"""Unit tests for Message value objects and ContentBlock JSON round-trips. Pure — no I/O."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffer.domain.chat.message import (
    ContentBlock,
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    block_from_dict,
    block_to_dict,
)

# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


def test_role_values() -> None:
    assert Role.USER == "user"
    assert Role.ASSISTANT == "assistant"


# ---------------------------------------------------------------------------
# TextBlock
# ---------------------------------------------------------------------------


def test_text_block_frozen() -> None:
    block = TextBlock(text="hello")
    assert block.text == "hello"
    assert block.type == "text"
    with pytest.raises((AttributeError, TypeError)):
        block.text = "other"  # type: ignore[misc]


def test_text_block_round_trip() -> None:
    block = TextBlock(text="hello world")
    d = block_to_dict(block)
    assert d == {"type": "text", "text": "hello world"}
    restored = block_from_dict(d)
    assert restored == block


# ---------------------------------------------------------------------------
# ToolUseBlock
# ---------------------------------------------------------------------------


def test_tool_use_block_round_trip() -> None:
    block = ToolUseBlock(
        tool_use_id="tu-123",
        tool_name="coffer__search_memory",
        tool_input={"query": "OAuth"},
    )
    assert block.type == "tool_use"
    d = block_to_dict(block)
    assert d["type"] == "tool_use"
    assert d["tool_use_id"] == "tu-123"
    assert d["tool_name"] == "coffer__search_memory"
    assert d["tool_input"] == {"query": "OAuth"}
    restored = block_from_dict(d)
    assert restored == block


def test_tool_use_block_frozen() -> None:
    block = ToolUseBlock(tool_use_id="x", tool_name="foo", tool_input={})
    with pytest.raises((AttributeError, TypeError)):
        block.tool_name = "bar"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ToolResultBlock
# ---------------------------------------------------------------------------


def test_tool_result_block_success_round_trip() -> None:
    block = ToolResultBlock(
        tool_use_id="tu-123",
        tool_name="coffer__search_memory",
        output={"results": ["r1", "r2"]},
        error=None,
    )
    assert block.type == "tool_result"
    d = block_to_dict(block)
    assert d["output"] == {"results": ["r1", "r2"]}
    assert d["error"] is None
    restored = block_from_dict(d)
    assert restored == block


def test_tool_result_block_error_round_trip() -> None:
    block = ToolResultBlock(
        tool_use_id="tu-456",
        tool_name="coffer__kb_search",
        output=None,
        error="KB not found",
    )
    d = block_to_dict(block)
    assert d["output"] is None
    assert d["error"] == "KB not found"
    restored = block_from_dict(d)
    assert restored == block


# ---------------------------------------------------------------------------
# block_from_dict — unknown type raises
# ---------------------------------------------------------------------------


def test_block_from_dict_unknown_type() -> None:
    with pytest.raises(ValueError, match=r"unknown.*type"):
        block_from_dict({"type": "image"})


def test_block_from_dict_missing_required_field_raises_value_error() -> None:
    with pytest.raises(ValueError):
        block_from_dict({"type": "text"})  # missing required field 'text'


# ---------------------------------------------------------------------------
# ContentBlock union (type annotation check)
# ---------------------------------------------------------------------------


def test_content_block_union_isinstance() -> None:
    blocks: list[ContentBlock] = [
        TextBlock(text="hi"),
        ToolUseBlock(tool_use_id="x", tool_name="f", tool_input={}),
        ToolResultBlock(tool_use_id="x", tool_name="f", output={"k": "v"}, error=None),
    ]
    for b in blocks:
        assert isinstance(b, (TextBlock, ToolUseBlock, ToolResultBlock))


# ---------------------------------------------------------------------------
# Message entity
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


def test_message_user_fields() -> None:
    msg = Message(
        id="m-001",
        conversation_id="c-001",
        seq=0,
        role=Role.USER,
        content=[TextBlock(text="hello")],
        status="complete",
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=_utcnow(),
    )
    assert msg.role == "user"
    assert msg.status == "complete"
    assert msg.model_id is None
    assert msg.prompt_tokens is None


def test_message_assistant_fields() -> None:
    msg = Message(
        id="m-002",
        conversation_id="c-001",
        seq=1,
        role=Role.ASSISTANT,
        content=[
            TextBlock(text="hello back"),
            ToolUseBlock(tool_use_id="x", tool_name="f", tool_input={}),
        ],
        status="complete",
        model_id="model-abc",
        prompt_tokens=100,
        completion_tokens=42,
        created_at=_utcnow(),
    )
    assert msg.role == "assistant"
    assert msg.model_id == "model-abc"
    assert msg.prompt_tokens == 100
    assert msg.completion_tokens == 42


def test_message_frozen() -> None:
    msg = Message(
        id="m-003",
        conversation_id="c-001",
        seq=0,
        role=Role.USER,
        content=[TextBlock(text="hi")],
        status="complete",
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=_utcnow(),
    )
    with pytest.raises((AttributeError, TypeError)):
        msg.role = "assistant"  # type: ignore[misc]


def test_message_status_values() -> None:
    """All three statuses are accepted."""
    base = {
        "id": "m",
        "conversation_id": "c",
        "seq": 0,
        "role": Role.USER,
        "content": [],
        "model_id": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "created_at": _utcnow(),
    }
    for status in ("complete", "streaming", "failed"):
        msg = Message(**base, status=status)  # type: ignore[arg-type]
        assert msg.status == status


# ---------------------------------------------------------------------------
# JSON serialisation helpers used by the persistence layer
# ---------------------------------------------------------------------------


def test_block_list_json_round_trip() -> None:
    """Simulate what the persistence layer does: JSON encode + decode a content list."""
    blocks: list[ContentBlock] = [
        TextBlock(text="hi"),
        ToolUseBlock(tool_use_id="u1", tool_name="tool", tool_input={"k": 1}),
        ToolResultBlock(tool_use_id="u1", tool_name="tool", output={"r": "ok"}, error=None),
    ]
    raw = json.dumps([block_to_dict(b) for b in blocks])
    decoded = [block_from_dict(d) for d in json.loads(raw)]
    assert decoded == blocks
