"""Map ACP ``session/update`` notifications to Coffer ``AgentEvent``s.

The hermes analog of ``codex_mapping.map_codex_notification``: each streamed ACP
``session/update`` notification becomes zero or more ``AgentEvent``s, threaded
through a mutable :class:`HermesParseState`.

ACP ``session/update`` params shape::

    {"sessionId": ..., "update": {"sessionUpdate": "<variant>", ...}}

Variants handled (§ Agent Client Protocol ``SessionNotification``):

* ``agent_message_chunk``  → ``TextDelta`` from ``content.text``. ACP chunks are
  **incremental** — emitted verbatim (never diffed/accumulated).
* ``agent_thought_chunk``  → ``[]`` (reasoning is not surfaced).
* ``tool_call``            → ``ToolCall`` (once per ``toolCallId``); the tool name
  is remembered so a later ``tool_call_update`` can reference it.
* ``tool_call_update``     → on ``status`` ``completed``/``failed`` a ``ToolResult``
  (once per ``toolCallId``); ignored for other statuses (``pending`` /
  ``in_progress``).
* ``plan`` / ``available_commands_update`` / ``user_message_chunk`` /
  ``current_mode_update`` and anything else → ``[]``.

No terminal (``TurnDone``/``TurnError``) is ever emitted here — the adapter
synthesises the terminal from the ``session/prompt`` response's ``stopReason``.

Every accessor is defensive (``.get`` + ``isinstance``) so an odd or partial
frame maps to ``[]`` rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
)


@dataclass
class HermesParseState:
    """Mutable state threaded through ACP ``session/update`` mapping for one turn."""

    session_id: str | None = None
    #: toolCallId -> the tool name captured from the initial ``tool_call``.
    tool_names: dict[str, str] = field(default_factory=dict)
    #: toolCallIds already surfaced as a ``ToolCall`` (de-dup).
    seen_calls: set[str] = field(default_factory=set)
    #: toolCallIds already surfaced as a ``ToolResult`` (de-dup).
    seen_results: set[str] = field(default_factory=set)
    terminal_emitted: bool = False


def map_hermes_update(params: dict[str, Any], state: HermesParseState) -> list[AgentEvent]:
    """Map one ACP ``session/update`` notification to zero or more ``AgentEvent``s."""
    update = params.get("update")
    if not isinstance(update, dict):
        return []
    variant = update.get("sessionUpdate")
    if variant == "agent_message_chunk":
        text = _content_text(update.get("content"))
        return [TextDelta(text=text)] if text else []
    if variant == "tool_call":
        return _tool_call(update, state)
    if variant == "tool_call_update":
        return _tool_call_update(update, state)
    # agent_thought_chunk, plan, available_commands_update, user_message_chunk,
    # current_mode_update, and any unknown variant — nothing to surface.
    return []


def _content_text(content: Any) -> str:
    """Extract text from an ACP ``ContentBlock`` (or a list of them)."""
    if isinstance(content, dict):
        if content.get("type") == "text":
            text = content.get("text")
            return text if isinstance(text, str) else ""
        return ""
    if isinstance(content, list):
        return "".join(_content_text(block) for block in content)
    return ""


def _tool_call(update: dict[str, Any], state: HermesParseState) -> list[AgentEvent]:
    tid = update.get("toolCallId")
    if not isinstance(tid, str) or not tid or tid in state.seen_calls:
        return []
    state.seen_calls.add(tid)
    name = update.get("title") or update.get("kind") or "tool"
    name = str(name)
    state.tool_names[tid] = name
    raw = update.get("rawInput")
    tool_input = raw if isinstance(raw, dict) else {}
    return [ToolCall(tool_use_id=tid, tool_name=name, tool_input=tool_input)]


def _tool_call_update(update: dict[str, Any], state: HermesParseState) -> list[AgentEvent]:
    tid = update.get("toolCallId")
    if not isinstance(tid, str) or not tid:
        return []
    status = update.get("status")
    if status not in ("completed", "failed"):
        return []
    if tid in state.seen_results:
        return []
    state.seen_results.add(tid)
    name = state.tool_names.get(tid, "tool")
    is_error = status == "failed"

    raw_output = update.get("rawOutput")
    output: dict[str, Any] | None = raw_output if isinstance(raw_output, dict) else None
    if output is None:
        content = update.get("content")
        if content is not None:
            output = {"content": content}

    if is_error:
        return [
            ToolResult(
                tool_use_id=tid,
                tool_name=name,
                output=None,
                error=_error_text(output) or "tool call failed",
            )
        ]
    return [ToolResult(tool_use_id=tid, tool_name=name, output=output, error=None)]


def _error_text(output: dict[str, Any] | None) -> str | None:
    """Best-effort human-readable error from a failed tool's raw output."""
    if not isinstance(output, dict):
        return None
    for key in ("error", "message", "stderr"):
        value = output.get(key)
        if isinstance(value, str) and value:
            return value
    return None


__all__ = ["HermesParseState", "map_hermes_update"]
