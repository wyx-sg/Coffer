"""Unit tests for ``map_opencode_event`` (spec 008 / ADR-040).

Pure, table-driven over opencode's real ``part`` shapes (from its OpenAPI schema
and on-disk ``part`` store): text deltas (in-place full-text accumulation →
incremental deltas), tool call+result once, step-finish token accumulation,
session-id capture, the ``message.part.updated`` event envelope, and the
synthetic/ignored/unknown → ``[]`` rules. The terminal ``TurnDone``/``TurnError``
is the adapter's job (on process exit), NOT the mapper's — a ``step-finish`` is a
step finishing, not the turn.
"""

from __future__ import annotations

from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult
from coffer.infrastructure.chat.opencode_mapping import (
    OpencodeParseState,
    map_opencode_event,
)


def test_text_part_accumulates_into_incremental_deltas() -> None:
    state = OpencodeParseState()
    assert map_opencode_event({"type": "text", "id": "p1", "text": "he"}, state) == [
        TextDelta(text="he")
    ]
    # opencode re-emits the SAME part with the full text so far → emit only the tail.
    assert map_opencode_event({"type": "text", "id": "p1", "text": "hello"}, state) == [
        TextDelta(text="llo")
    ]
    # No new content → nothing.
    assert map_opencode_event({"type": "text", "id": "p1", "text": "hello"}, state) == []


def test_synthetic_and_ignored_text_are_dropped() -> None:
    state = OpencodeParseState()
    assert (
        map_opencode_event({"type": "text", "id": "s", "text": "x", "synthetic": True}, state) == []
    )
    assert (
        map_opencode_event({"type": "text", "id": "i", "text": "x", "ignored": True}, state) == []
    )


def test_tool_part_emits_call_then_result_once() -> None:
    state = OpencodeParseState()
    part = {
        "type": "tool",
        "tool": "webfetch",
        "callID": "c1",
        "state": {"status": "completed", "input": {"url": "x"}, "output": "done"},
    }
    events = map_opencode_event(part, state)
    assert events == [
        ToolCall(tool_use_id="c1", tool_name="webfetch", tool_input={"url": "x"}),
        ToolResult(tool_use_id="c1", tool_name="webfetch", output={"output": "done"}, error=None),
    ]
    # A repeated update for the same call must not duplicate either event.
    assert map_opencode_event(part, state) == []


def test_tool_running_then_completed_across_two_updates() -> None:
    state = OpencodeParseState()
    running = {
        "type": "tool",
        "tool": "bash",
        "callID": "c2",
        "state": {"status": "running", "input": {"command": "ls"}},
    }
    completed = {
        "type": "tool",
        "tool": "bash",
        "callID": "c2",
        "state": {"status": "completed", "input": {"command": "ls"}, "output": "a\nb"},
    }
    assert map_opencode_event(running, state) == [
        ToolCall(tool_use_id="c2", tool_name="bash", tool_input={"command": "ls"})
    ]
    assert map_opencode_event(completed, state) == [
        ToolResult(tool_use_id="c2", tool_name="bash", output={"output": "a\nb"}, error=None)
    ]


def test_tool_error_state_carries_error() -> None:
    state = OpencodeParseState()
    part = {
        "type": "tool",
        "tool": "bash",
        "callID": "c3",
        "state": {"status": "error", "input": {}, "error": "boom"},
    }
    events = map_opencode_event(part, state)
    assert events == [
        ToolCall(tool_use_id="c3", tool_name="bash", tool_input={}),
        ToolResult(tool_use_id="c3", tool_name="bash", output=None, error="boom"),
    ]


def test_step_finish_accumulates_tokens_and_emits_nothing() -> None:
    state = OpencodeParseState()
    assert (
        map_opencode_event(
            {"type": "step-finish", "reason": "stop", "tokens": {"input": 100, "output": 5}},
            state,
        )
        == []
    )
    map_opencode_event(
        {"type": "step-finish", "reason": "stop", "tokens": {"input": 120, "output": 7}}, state
    )
    assert state.prompt_tokens == 120  # last step's input
    assert state.completion_tokens == 12  # 5 + 7 accumulated


def test_event_envelope_is_unwrapped() -> None:
    state = OpencodeParseState()
    events = map_opencode_event(
        {
            "type": "message.part.updated",
            "properties": {
                "part": {"type": "text", "id": "q", "text": "hi", "sessionID": "ses_env"}
            },
        },
        state,
    )
    assert events == [TextDelta(text="hi")]
    assert state.session_id == "ses_env"


def test_session_id_captured_from_raw_part() -> None:
    state = OpencodeParseState()
    map_opencode_event({"type": "text", "id": "z", "text": "x", "sessionID": "ses_abc"}, state)
    assert state.session_id == "ses_abc"


def test_delta_envelope_is_emitted_incrementally_not_diffed() -> None:
    state = OpencodeParseState()
    # A `.delta` chunk carries incremental text appended verbatim — successive
    # chunks must BOTH survive (diffing them would collapse the stream).
    assert map_opencode_event(
        {
            "type": "message.part.delta",
            "properties": {"part": {"type": "text", "id": "d", "text": "He"}},
        },
        state,
    ) == [TextDelta(text="He")]
    assert map_opencode_event(
        {
            "type": "message.part.delta",
            "properties": {"part": {"type": "text", "id": "d", "text": "llo"}},
        },
        state,
    ) == [TextDelta(text="llo")]


def test_session_id_ignores_non_session_shaped_values() -> None:
    state = OpencodeParseState()
    # A messageID-shaped value must never be mistaken for the session id.
    map_opencode_event({"type": "text", "id": "p", "text": "x", "sessionID": "msg_123"}, state)
    assert state.session_id is None
    map_opencode_event({"type": "text", "id": "p2", "text": "y", "sessionID": "ses_ok"}, state)
    assert state.session_id == "ses_ok"


def test_unknown_and_structural_parts_yield_nothing() -> None:
    state = OpencodeParseState()
    for part in (
        {"type": "step-start"},
        {"type": "reasoning", "text": "thinking"},
        {"type": "snapshot"},
        {"no_type_field": True},
    ):
        assert map_opencode_event(part, state) == []
