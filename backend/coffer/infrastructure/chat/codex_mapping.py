"""Map ``codex app-server`` notifications to Coffer ``AgentEvent``s (spec 008, T3).

The Codex analog of ``claude_sdk_agent.map_sdk_message``: each streamed
server→client notification ``(method, params)`` becomes zero or more
``AgentEvent``s, threaded through a mutable :class:`CodexParseState` (mirrors
``adapter_support.ParseState``). Protocol shapes verified empirically against codex-cli 0.125.0
(``codex app-server generate-json-schema``).

Mapping rules (§A):

* ``thread/started``            → capture ``thread.id`` (the resumable session id).
* ``turn/started``              → capture ``turn.id``.
* ``item/agentMessage/delta``   → ``TextDelta(delta)``.
* ``item/started``              → ``[]`` (item content is partial; de-dup — content is
                                  emitted only on ``item/completed``).
* ``item/completed`` (commandExecution) → ``ToolCall(tool_name="shell")`` + ``ToolResult``.
* ``item/completed`` (fileChange)       → ``ToolCall(tool_name="file_change")`` + ``ToolResult``.
* ``thread/tokenUsage/updated`` → stash ``last.input/outputTokens`` for ``TurnDone``.
* ``turn/completed``            → terminal ``TurnDone`` (stashed tokens).
* ``error`` (``willRetry==false``) → terminal ``TurnError``.
* anything else                 → ``[]``.

Exactly one terminal (``TurnDone``/``TurnError``) is emitted per turn: once
``state.terminal_emitted`` is set, later terminal-eligible notifications map to
``[]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)


@dataclass
class CodexParseState:
    """Mutable state threaded through Codex notification mapping for one turn."""

    session_id: str | None = None
    turn_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False


def map_codex_notification(
    method: str, params: dict[str, Any], state: CodexParseState
) -> list[AgentEvent]:
    """Map one Codex notification to zero or more ``AgentEvent``s."""
    if method == "thread/started":
        thread = params.get("thread") or {}
        tid = thread.get("id")
        if tid:
            state.session_id = tid
        return []
    if method == "turn/started":
        turn = params.get("turn") or {}
        if turn.get("id"):
            state.turn_id = turn["id"]
        return []
    if method == "item/agentMessage/delta":
        delta = params.get("delta") or ""
        return [TextDelta(text=delta)] if delta else []
    if method == "item/started":
        return []
    if method == "item/completed":
        return _item_completed(params)
    if method == "thread/tokenUsage/updated":
        _stash_tokens(params, state)
        return []
    if method == "turn/completed":
        return _terminal(
            state,
            TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            ),
        )
    if method == "error":
        if params.get("willRetry"):
            return []
        message = (params.get("error") or {}).get("message") or "codex error"
        return _terminal(state, TurnError(code="codex_error", message=str(message)))
    return []


def _terminal(state: CodexParseState, event: AgentEvent) -> list[AgentEvent]:
    """Emit ``event`` once; suppress any subsequent terminal for the turn."""
    if state.terminal_emitted:
        return []
    state.terminal_emitted = True
    return [event]


def _stash_tokens(params: dict[str, Any], state: CodexParseState) -> None:
    last = (params.get("tokenUsage") or {}).get("last") or {}
    if "inputTokens" in last:
        state.prompt_tokens = last.get("inputTokens")
    if "outputTokens" in last:
        state.completion_tokens = last.get("outputTokens")


def _item_completed(params: dict[str, Any]) -> list[AgentEvent]:
    item = params.get("item") or {}
    item_type = item.get("type")
    if item_type == "commandExecution":
        return _command_execution(item)
    if item_type == "fileChange":
        return _file_change(item)
    # agentMessage / mcpToolCall / dynamicToolCall etc. — text already streamed
    # via deltas; nothing else to surface in v1.
    return []


def _command_execution(item: dict[str, Any]) -> list[AgentEvent]:
    item_id = str(item.get("id") or "")
    command = item.get("command")
    cwd = item.get("cwd")
    status = item.get("status")
    exit_code = item.get("exitCode")
    output = item.get("aggregatedOutput") or ""
    is_error = status == "failed" or (exit_code is not None and exit_code != 0)
    call = ToolCall(
        tool_use_id=item_id,
        tool_name="shell",
        tool_input={"command": command, "cwd": cwd},
    )
    result = ToolResult(
        tool_use_id=item_id,
        tool_name="shell",
        output=None if is_error else {"content": output, "exit_code": exit_code},
        error=output or f"command failed (exit {exit_code})" if is_error else None,
    )
    return [call, result]


def _file_change(item: dict[str, Any]) -> list[AgentEvent]:
    item_id = str(item.get("id") or "")
    changes = item.get("changes") or []
    status = item.get("status")
    is_error = status == "failed"
    call = ToolCall(
        tool_use_id=item_id,
        tool_name="file_change",
        tool_input={"changes": changes},
    )
    result = ToolResult(
        tool_use_id=item_id,
        tool_name="file_change",
        output=None if is_error else {"status": status},
        error=f"file change failed (status {status})" if is_error else None,
    )
    return [call, result]


__all__ = ["CodexParseState", "map_codex_notification"]
