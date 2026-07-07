"""Unit tests for ``map_hermes_update`` — ACP ``session/update`` → ``AgentEvent``.

Covers the variants the adapter relies on:
- ``agent_message_chunk`` → ``TextDelta`` emitted **verbatim** (ACP chunks are
  incremental, never diffed/accumulated).
- ``tool_call`` + ``tool_call_update`` → one ``ToolCall`` then one ``ToolResult``
  (de-duped by ``toolCallId``, tool name carried across).
- ignored variants map to ``[]``.
- tolerance: garbage / missing / mis-typed fields never raise.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult
from coffer.infrastructure.chat.hermes_mapping import HermesParseState, map_hermes_update


def _update(variant: str, **fields: Any) -> dict[str, Any]:
    """Wrap an ACP ``update`` body in the ``session/update`` params envelope."""
    return {"sessionId": "ses-1", "update": {"sessionUpdate": variant, **fields}}


# ---------------------------------------------------------------------------
# agent_message_chunk → TextDelta (verbatim)
# ---------------------------------------------------------------------------


def test_agent_message_chunk_emits_text_delta_verbatim() -> None:
    state = HermesParseState()
    params = _update("agent_message_chunk", content={"type": "text", "text": "Hello"})
    assert map_hermes_update(params, state) == [TextDelta(text="Hello")]


def test_agent_message_chunks_are_not_accumulated() -> None:
    # Two consecutive chunks are emitted as two independent deltas — no diffing.
    state = HermesParseState()
    out1 = map_hermes_update(
        _update("agent_message_chunk", content={"type": "text", "text": "Hel"}), state
    )
    out2 = map_hermes_update(
        _update("agent_message_chunk", content={"type": "text", "text": "lo"}), state
    )
    assert out1 == [TextDelta(text="Hel")]
    assert out2 == [TextDelta(text="lo")]


def test_empty_text_chunk_is_dropped() -> None:
    state = HermesParseState()
    assert (
        map_hermes_update(
            _update("agent_message_chunk", content={"type": "text", "text": ""}), state
        )
        == []
    )


# ---------------------------------------------------------------------------
# ignored variants
# ---------------------------------------------------------------------------


def test_thought_and_other_variants_are_ignored() -> None:
    state = HermesParseState()
    for variant in (
        "agent_thought_chunk",
        "plan",
        "available_commands_update",
        "user_message_chunk",
        "current_mode_update",
        "some_future_variant",
    ):
        assert (
            map_hermes_update(_update(variant, content={"type": "text", "text": "x"}), state) == []
        )


# ---------------------------------------------------------------------------
# tool_call + tool_call_update → ToolCall + ToolResult
# ---------------------------------------------------------------------------


def test_tool_call_then_completed_update_emits_call_and_result_once() -> None:
    state = HermesParseState()
    call = map_hermes_update(
        _update(
            "tool_call", toolCallId="t1", title="Read file", kind="read", rawInput={"path": "/a"}
        ),
        state,
    )
    assert call == [ToolCall(tool_use_id="t1", tool_name="Read file", tool_input={"path": "/a"})]

    result = map_hermes_update(
        _update(
            "tool_call_update", toolCallId="t1", status="completed", rawOutput={"content": "ok"}
        ),
        state,
    )
    assert result == [
        ToolResult(tool_use_id="t1", tool_name="Read file", output={"content": "ok"}, error=None)
    ]

    # Duplicate call / result frames for the same id are suppressed.
    assert map_hermes_update(_update("tool_call", toolCallId="t1", title="Read file"), state) == []
    assert (
        map_hermes_update(_update("tool_call_update", toolCallId="t1", status="completed"), state)
        == []
    )


def test_tool_call_name_falls_back_to_kind_then_default() -> None:
    state = HermesParseState()
    out = map_hermes_update(_update("tool_call", toolCallId="t2", kind="execute"), state)
    assert out == [ToolCall(tool_use_id="t2", tool_name="execute", tool_input={})]

    out2 = map_hermes_update(_update("tool_call", toolCallId="t3"), state)
    assert out2 == [ToolCall(tool_use_id="t3", tool_name="tool", tool_input={})]


def test_tool_call_update_in_progress_is_ignored() -> None:
    state = HermesParseState()
    map_hermes_update(_update("tool_call", toolCallId="t1", title="X"), state)
    assert (
        map_hermes_update(_update("tool_call_update", toolCallId="t1", status="in_progress"), state)
        == []
    )
    assert (
        map_hermes_update(_update("tool_call_update", toolCallId="t1", status="pending"), state)
        == []
    )


def test_failed_tool_call_update_emits_error_result() -> None:
    state = HermesParseState()
    map_hermes_update(_update("tool_call", toolCallId="t9", title="Run"), state)
    out = map_hermes_update(
        _update("tool_call_update", toolCallId="t9", status="failed", rawOutput={"error": "boom"}),
        state,
    )
    assert out == [ToolResult(tool_use_id="t9", tool_name="Run", output=None, error="boom")]


def test_completed_update_uses_content_when_no_raw_output() -> None:
    state = HermesParseState()
    map_hermes_update(_update("tool_call", toolCallId="tc", title="Grep"), state)
    out = map_hermes_update(
        _update(
            "tool_call_update",
            toolCallId="tc",
            status="completed",
            content=[{"type": "content", "content": {"type": "text", "text": "hit"}}],
        ),
        state,
    )
    assert len(out) == 1
    res = out[0]
    assert isinstance(res, ToolResult)
    assert res.tool_use_id == "tc"
    assert res.tool_name == "Grep"
    assert res.output == {
        "content": [{"type": "content", "content": {"type": "text", "text": "hit"}}]
    }
    assert res.error is None


def test_result_without_prior_call_defaults_tool_name() -> None:
    # A tool_call_update whose toolCallId was never introduced still yields a
    # ToolResult (default tool name) rather than crashing.
    state = HermesParseState()
    out = map_hermes_update(
        _update("tool_call_update", toolCallId="orphan", status="completed"), state
    )
    assert out == [ToolResult(tool_use_id="orphan", tool_name="tool", output=None, error=None)]


# ---------------------------------------------------------------------------
# tolerance — never raise on odd input
# ---------------------------------------------------------------------------


def test_tolerant_of_garbage_and_missing_fields() -> None:
    state = HermesParseState()
    assert map_hermes_update({}, state) == []
    assert map_hermes_update({"update": None}, state) == []
    assert map_hermes_update({"update": "not-a-dict"}, state) == []
    assert map_hermes_update({"update": {}}, state) == []  # no sessionUpdate
    assert map_hermes_update(_update("agent_message_chunk"), state) == []  # no content
    assert map_hermes_update(_update("agent_message_chunk", content="nope"), state) == []
    assert map_hermes_update(_update("tool_call"), state) == []  # no toolCallId
    assert map_hermes_update(_update("tool_call", toolCallId=123), state) == []  # wrong type
    assert map_hermes_update(_update("tool_call", toolCallId="t", rawInput="nope"), state) == [
        ToolCall(tool_use_id="t", tool_name="tool", tool_input={})
    ]
    assert map_hermes_update(_update("tool_call_update", status="completed"), state) == []  # no id


def test_never_terminal() -> None:
    # The mapper never synthesises a terminal — the adapter does that from the
    # session/prompt response.
    state = HermesParseState()
    for variant in ("agent_message_chunk", "tool_call", "tool_call_update"):
        map_hermes_update(
            _update(
                variant, content={"type": "text", "text": "x"}, toolCallId="z", status="completed"
            ),
            state,
        )
    assert state.terminal_emitted is False


def test_synchronously_completed_tool_call_yields_call_and_result() -> None:
    # A tool that ran instantly can carry a terminal status on the tool_call frame
    # itself, with no follow-up tool_call_update — both events must be emitted, else
    # the UI spins on that call forever.
    state = HermesParseState()
    events = map_hermes_update(
        _update(
            "tool_call",
            toolCallId="c1",
            title="Bash",
            status="completed",
            rawInput={"cmd": "ls"},
            rawOutput={"stdout": "a"},
        ),
        state,
    )
    assert [type(e).__name__ for e in events] == ["ToolCall", "ToolResult"]
    assert events[0] == ToolCall(tool_use_id="c1", tool_name="Bash", tool_input={"cmd": "ls"})
    assert isinstance(events[1], ToolResult) and events[1].error is None
    # A stray later update for the same id must not duplicate the result.
    assert (
        map_hermes_update(_update("tool_call_update", toolCallId="c1", status="completed"), state)
        == []
    )
