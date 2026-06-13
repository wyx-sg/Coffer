"""Unit tests for ``map_codex_notification`` (spec 008, T3).

Pure, table-driven: each canned ``(method, params)`` notification maps to the
expected list of ``AgentEvent``s. Covers text deltas, command/file-change
completions (ok + failed), thread-id capture, token stashing, the single
terminal ``TurnDone`` (with stashed tokens), ``error`` → ``TurnError``, and the
de-dup / unknown → ``[]`` rules. Mirrors ``map_sdk_message`` semantics.
"""

from __future__ import annotations

from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.infrastructure.chat.codex_mapping import (
    CodexParseState,
    map_codex_notification,
)


def test_thread_started_captures_session_id() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "thread/started", {"thread": {"id": "thread-123", "path": "/x.jsonl"}}, state
    )
    assert events == []
    assert state.session_id == "thread-123"


def test_turn_started_captures_turn_id() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "turn/started", {"threadId": "t", "turn": {"id": "turn-9"}}, state
    )
    assert events == []
    assert state.turn_id == "turn-9"


def test_agent_message_delta_maps_to_text_delta() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "item/agentMessage/delta",
        {"threadId": "t", "turnId": "u", "itemId": "i", "delta": "hello"},
        state,
    )
    assert events == [TextDelta(text="hello")]


def test_empty_delta_yields_nothing() -> None:
    state = CodexParseState()
    assert map_codex_notification("item/agentMessage/delta", {"delta": ""}, state) == []


def test_item_started_is_ignored() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "item/started",
        {"item": {"type": "commandExecution", "id": "c1", "command": "ls"}},
        state,
    )
    assert events == []


def test_command_execution_completed_ok() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "item/completed",
        {
            "item": {
                "type": "commandExecution",
                "id": "c1",
                "command": "ls -la",
                "cwd": "/repo",
                "status": "completed",
                "exitCode": 0,
                "aggregatedOutput": "file1\nfile2\n",
            }
        },
        state,
    )
    assert events == [
        ToolCall(
            tool_use_id="c1", tool_name="shell", tool_input={"command": "ls -la", "cwd": "/repo"}
        ),
        ToolResult(
            tool_use_id="c1",
            tool_name="shell",
            output={"content": "file1\nfile2\n", "exit_code": 0},
            error=None,
        ),
    ]


def test_command_execution_completed_failed() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "item/completed",
        {
            "item": {
                "type": "commandExecution",
                "id": "c2",
                "command": "false",
                "status": "failed",
                "exitCode": 1,
                "aggregatedOutput": "boom\n",
            }
        },
        state,
    )
    assert events[0] == ToolCall(
        tool_use_id="c2", tool_name="shell", tool_input={"command": "false", "cwd": None}
    )
    result = events[1]
    assert isinstance(result, ToolResult)
    assert result.output is None
    assert result.error is not None and "boom" in result.error


def test_file_change_completed() -> None:
    state = CodexParseState()
    changes = [{"path": "a.py", "kind": "modify"}]
    events = map_codex_notification(
        "item/completed",
        {"item": {"type": "fileChange", "id": "f1", "changes": changes, "status": "completed"}},
        state,
    )
    assert events == [
        ToolCall(tool_use_id="f1", tool_name="file_change", tool_input={"changes": changes}),
        ToolResult(
            tool_use_id="f1",
            tool_name="file_change",
            output={"status": "completed"},
            error=None,
        ),
    ]


def test_token_usage_is_stashed_not_emitted() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "thread/tokenUsage/updated",
        {
            "threadId": "t",
            "turnId": "u",
            "tokenUsage": {"last": {"inputTokens": 120, "outputTokens": 34}},
        },
        state,
    )
    assert events == []
    assert state.prompt_tokens == 120
    assert state.completion_tokens == 34


def test_turn_completed_uses_stashed_tokens_and_is_terminal() -> None:
    state = CodexParseState()
    map_codex_notification(
        "thread/tokenUsage/updated",
        {"tokenUsage": {"last": {"inputTokens": 7, "outputTokens": 11}}},
        state,
    )
    events = map_codex_notification(
        "turn/completed", {"threadId": "t", "turn": {"id": "u", "status": "completed"}}, state
    )
    assert events == [TurnDone(prompt_tokens=7, completion_tokens=11, stop_reason="end_turn")]
    assert state.terminal_emitted is True


def test_error_no_retry_is_terminal_turn_error() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "error",
        {"error": {"message": "model unavailable"}, "willRetry": False},
        state,
    )
    assert events == [TurnError(code="codex_error", message="model unavailable")]
    assert state.terminal_emitted is True


def test_error_will_retry_is_not_terminal() -> None:
    state = CodexParseState()
    events = map_codex_notification(
        "error", {"error": {"message": "transient"}, "willRetry": True}, state
    )
    assert events == []
    assert state.terminal_emitted is False


def test_unknown_method_yields_nothing() -> None:
    state = CodexParseState()
    assert map_codex_notification("item/reasoning/delta", {"delta": "x"}, state) == []
    assert map_codex_notification("turn/diff/updated", {}, state) == []


def test_only_one_terminal_emitted() -> None:
    """A second terminal-eligible notification must not double-emit."""
    state = CodexParseState()
    first = map_codex_notification("turn/completed", {"turn": {"id": "u"}}, state)
    assert len(first) == 1 and isinstance(first[0], TurnDone)
    second = map_codex_notification(
        "error", {"error": {"message": "late"}, "willRetry": False}, state
    )
    assert second == []
