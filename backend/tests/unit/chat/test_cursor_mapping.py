"""Unit tests for ``map_cursor_event`` (cursor-agent stream-json NDJSON → events).

Pure, table-driven over Cursor's documented ``--output-format stream-json``
shapes: assistant text emitted verbatim (single + multi-block), tool
started+completed → ``ToolCall``+``ToolResult`` once, a synchronously-completed
tool still yielding both, ``system`` init → session capture, ``user`` ignored,
the ``result`` marker recording ``is_error`` (no terminal from the mapper), and
tolerance of garbage. The terminal ``TurnDone``/``TurnError`` is the adapter's
job (on process exit), NOT the mapper's.
"""

from __future__ import annotations

from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult
from coffer.infrastructure.chat.cursor_mapping import CursorParseState, map_cursor_event


def test_assistant_text_is_emitted_verbatim() -> None:
    state = CursorParseState()
    obj = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        "session_id": "sess-1",
    }
    assert map_cursor_event(obj, state) == [TextDelta(text="hello")]


def test_assistant_segments_are_not_diffed_or_accumulated() -> None:
    state = CursorParseState()
    # Each assistant event is a distinct complete segment (between tool calls),
    # NOT a cumulative snapshot — successive segments must both survive verbatim.
    first = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "He"}]},
    }
    second = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "llo"}]},
    }
    assert map_cursor_event(first, state) == [TextDelta(text="He")]
    assert map_cursor_event(second, state) == [TextDelta(text="llo")]


def test_assistant_multi_block_text_is_concatenated() -> None:
    state = CursorParseState()
    obj = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "foo "},
                {"type": "text", "text": "bar"},
            ],
        },
    }
    assert map_cursor_event(obj, state) == [TextDelta(text="foo bar")]


def test_assistant_empty_or_non_text_content_yields_nothing() -> None:
    state = CursorParseState()
    assert map_cursor_event({"type": "assistant", "message": {"content": []}}, state) == []
    assert (
        map_cursor_event({"type": "assistant", "message": {"content": [{"type": "image"}]}}, state)
        == []
    )


def test_tool_started_then_completed_emits_call_then_result_once() -> None:
    state = CursorParseState()
    started = {
        "type": "tool_call",
        "subtype": "started",
        "call_id": "c1",
        "tool_call": {"readToolCall": {"path": "/etc/hosts"}},
    }
    completed = {
        "type": "tool_call",
        "subtype": "completed",
        "call_id": "c1",
        "result": {"success": {"content": "127.0.0.1"}},
    }
    assert map_cursor_event(started, state) == [
        ToolCall(tool_use_id="c1", tool_name="read", tool_input={"path": "/etc/hosts"})
    ]
    assert map_cursor_event(completed, state) == [
        ToolResult(
            tool_use_id="c1",
            tool_name="read",
            output={"content": "127.0.0.1"},
            error=None,
        )
    ]
    # Repeated events must not duplicate either.
    assert map_cursor_event(started, state) == []
    assert map_cursor_event(completed, state) == []


def test_function_tool_call_derives_name_and_parses_string_args() -> None:
    state = CursorParseState()
    started = {
        "type": "tool_call",
        "subtype": "started",
        "call_id": "c2",
        "tool_call": {"function": {"name": "shell", "arguments": '{"command":"ls"}'}},
    }
    assert map_cursor_event(started, state) == [
        ToolCall(tool_use_id="c2", tool_name="shell", tool_input={"command": "ls"})
    ]


def test_write_tool_call_strips_suffix() -> None:
    state = CursorParseState()
    started = {
        "type": "tool_call",
        "subtype": "started",
        "call_id": "c3",
        "tool_call": {"writeToolCall": {"path": "a.txt", "contents": "hi"}},
    }
    assert map_cursor_event(started, state) == [
        ToolCall(
            tool_use_id="c3",
            tool_name="write",
            tool_input={"path": "a.txt", "contents": "hi"},
        )
    ]


def test_sync_completed_without_prior_started_yields_both_once() -> None:
    state = CursorParseState()
    # A completed event that never had a `started` still yields BOTH a ToolCall
    # and a ToolResult, exactly once.
    completed = {
        "type": "tool_call",
        "subtype": "completed",
        "call_id": "c4",
        "tool_call": {"readToolCall": {"path": "x"}},
        "result": {"success": {"content": "ok"}},
    }
    events = map_cursor_event(completed, state)
    assert events == [
        ToolCall(tool_use_id="c4", tool_name="read", tool_input={"path": "x"}),
        ToolResult(tool_use_id="c4", tool_name="read", output={"content": "ok"}, error=None),
    ]
    assert map_cursor_event(completed, state) == []


def test_tool_failure_result_carries_error() -> None:
    state = CursorParseState()
    started = {
        "type": "tool_call",
        "subtype": "started",
        "call_id": "c5",
        "tool_call": {"function": {"name": "shell", "arguments": {}}},
    }
    completed = {
        "type": "tool_call",
        "subtype": "completed",
        "call_id": "c5",
        "result": {"failure": "boom"},
    }
    map_cursor_event(started, state)
    assert map_cursor_event(completed, state) == [
        ToolResult(tool_use_id="c5", tool_name="shell", output=None, error="boom")
    ]


def test_system_init_captures_session_and_emits_nothing() -> None:
    state = CursorParseState()
    obj = {
        "type": "system",
        "subtype": "init",
        "session_id": "sess-abc",
        "model": "auto",
        "cwd": "/work",
        "permissionMode": "force",
    }
    assert map_cursor_event(obj, state) == []
    assert state.session_id == "sess-abc"


def test_user_event_is_ignored() -> None:
    state = CursorParseState()
    obj = {"type": "user", "message": {"role": "user", "content": "hi"}, "session_id": "s"}
    assert map_cursor_event(obj, state) == []


def test_result_marker_records_is_error_without_emitting() -> None:
    ok = CursorParseState()
    assert (
        map_cursor_event(
            {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 12}, ok
        )
        == []
    )
    assert ok.is_error is False

    bad = CursorParseState()
    map_cursor_event({"type": "result", "subtype": "error", "is_error": True}, bad)
    assert bad.is_error is True


def test_tolerant_of_garbage_and_unknown_types() -> None:
    state = CursorParseState()
    for obj in (
        {},
        {"type": "assistant"},
        {"type": "assistant", "message": "not-a-dict"},
        {"type": "assistant", "message": {"content": 123}},  # non-str, non-list
        {"type": "tool_call"},
        {"type": "tool_call", "subtype": "started"},  # no call_id
        {"type": "tool_call", "subtype": "started", "call_id": 123},  # wrong type
        {"type": "result"},
        {"type": "wat"},
        {"no_type": True},
    ):
        assert map_cursor_event(obj, state) == []


def test_assistant_string_content_is_emitted() -> None:
    # Cursor mirrors the Anthropic Messages shape: content can be a bare STRING,
    # not just a list of blocks — it must not be dropped (review finding).
    state = CursorParseState()
    events = map_cursor_event(
        {"type": "assistant", "message": {"role": "assistant", "content": "hello world"}}, state
    )
    assert events == [TextDelta(text="hello world")]


def test_result_subtype_error_without_boolean_flag_marks_error() -> None:
    # A `result` need not carry a boolean is_error; a non-success subtype counts.
    state = CursorParseState()
    map_cursor_event({"type": "result", "subtype": "error"}, state)
    assert state.is_error is True


def test_tool_variant_ignores_sibling_metadata_keys() -> None:
    # _derive_tool must find the real variant, not the first key (which may be a
    # metadata sibling like `status`) — review finding.
    state = CursorParseState()
    events = map_cursor_event(
        {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "c1",
            "tool_call": {"status": "running", "readToolCall": {"path": "/x"}},
        },
        state,
    )
    assert events == [ToolCall(tool_use_id="c1", tool_name="read", tool_input={"path": "/x"})]
