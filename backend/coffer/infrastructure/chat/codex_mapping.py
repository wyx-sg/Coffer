"""Map ``codex app-server`` notifications to Coffer ``AgentEvent``s (spec chat).

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
* ``item/completed`` (agentMessage)     → ``MessageEnd(commentary=phase == "commentary")``.
* ``item/completed`` (commandExecution) → ``ToolCall(tool_name="shell")`` + ``ToolResult``.
* ``item/completed`` (fileChange)       → ``ToolCall(tool_name="file_change")`` + ``ToolResult``.
* ``item/completed`` (mcpToolCall, dynamicToolCall, webSearch, …) → ``ToolCall`` +
  ``ToolResult`` under the tool's own name, so every tool the agent runs separates
  the narration before it from the answer after it, as Claude Code's do.
* ``thread/tokenUsage/updated`` → stash ``last.input/outputTokens`` for ``TurnDone``.
* ``turn/completed``            → terminal ``TurnDone`` (stashed tokens).
* ``error`` (``willRetry==false``) → terminal ``TurnError``.
* anything else                 → ``[]``.

Exactly one terminal (``TurnDone``/``TurnError``) is emitted per turn: once
``state.terminal_emitted`` is set, later terminal-eligible notifications map to
``[]``.

One app-server carries more threads than the turn's own: Codex starts its
background memory consolidation agent there, and sub-agents the turn spawns run
as threads of their own. :func:`is_own_notification` keeps only the turn's
thread, so another thread's text never becomes the reply and its
``turn/completed`` never ends the turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.chat.events import (
    AgentEvent,
    MessageEnd,
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
    #: The thread this turn runs on, once ``thread/start|resume`` answered.
    thread_id: str | None = None
    #: The model the thread runs on, as the app-server reported it.
    model: str | None = None
    turn_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False


def is_own_notification(params: dict[str, Any], state: CodexParseState) -> bool:
    """Whether a notification belongs to this turn's thread.

    A notification that names no thread (process-wide) is kept. One that names
    a thread before the turn's own is known is another thread's: the turn's own
    notifications only start after ``turn/start``, which is sent once the
    thread id is known, and ``thread/start|resume`` already return that id.
    """
    thread_id = params.get("threadId")
    if thread_id is None:
        thread_id = (params.get("thread") or {}).get("id")
    if thread_id is None:
        return True
    return bool(thread_id == state.thread_id)


def map_codex_notification(
    method: str, params: dict[str, Any], state: CodexParseState
) -> list[AgentEvent]:
    """Map one Codex notification to zero or more ``AgentEvent``s."""
    if method == "thread/started":
        thread = params.get("thread") or {}
        tid = thread.get("id")
        if tid:
            state.session_id = tid
        state.model = thread.get("model") or params.get("model") or state.model
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
        return _item_completed(params, state)
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


def _item_completed(params: dict[str, Any], state: CodexParseState) -> list[AgentEvent]:
    item = params.get("item") or {}
    item_type = item.get("type")
    if item_type == "commandExecution":
        return _command_execution(item)
    if item_type == "fileChange":
        return _file_change(item, state)
    if item_type == "agentMessage":
        # Text already streamed via deltas; what is new is where the message ends
        # and whether the model marked it as narration. Codex's own surfaces treat
        # only ``final_answer`` text as the answer; ``None`` (an older model) is
        # "phase unknown" and stays answer text.
        return [MessageEnd(commentary=item.get("phase") == "commentary")]
    name = _tool_name(item)
    if name:
        return _other_tool(item, name)
    return []


#: The other items that are a tool the agent ran, by how each names itself.
_TOOL_ITEMS = {
    "mcpToolCall",
    "dynamicToolCall",
    "collabAgentToolCall",
    "webSearch",
    "imageView",
    "imageGeneration",
}


def _tool_name(item: dict[str, Any]) -> str:
    """The name a tool item shows as: ``mcp__<server>__<tool>`` for an MCP tool
    (Claude Code's spelling, so a tool reads the same from either agent), the
    tool's own name for a dynamic or sub-agent tool, else its item type."""
    item_type = item.get("type")
    if item_type not in _TOOL_ITEMS:
        return ""
    if item_type == "mcpToolCall":
        return f"mcp__{item.get('server') or 'mcp'}__{item.get('tool') or 'tool'}"
    if item_type in ("dynamicToolCall", "collabAgentToolCall"):
        return str(item.get("tool") or item_type)
    return str(item_type)


def _other_tool(item: dict[str, Any], name: str) -> list[AgentEvent]:
    item_id = str(item.get("id") or "")
    status = item.get("status")
    failed = status == "failed" or item.get("success") is False or bool(item.get("error"))
    tool_input: dict[str, Any] = {}
    if isinstance(item.get("arguments"), dict):
        tool_input = dict(item["arguments"])
    elif item.get("type") == "webSearch" and item.get("query"):
        tool_input = {"query": item["query"]}
    error = item.get("error")
    message = error.get("message") if isinstance(error, dict) else error
    return [
        ToolCall(tool_use_id=item_id, tool_name=name, tool_input=tool_input),
        ToolResult(
            tool_use_id=item_id,
            tool_name=name,
            output=None if failed else {"status": status},
            error=(str(message) if message else f"{name} failed") if failed else None,
        ),
    ]


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


def _file_change(item: dict[str, Any], state: CodexParseState) -> list[AgentEvent]:
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
