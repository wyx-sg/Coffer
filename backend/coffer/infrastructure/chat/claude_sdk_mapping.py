"""Map streamed Claude Agent SDK messages to ``AgentEvent``s.

Extracted from :mod:`claude_sdk_agent` (the file grew past its size budget). The
Codex analog is :mod:`codex_mapping`. Pure functions over a per-turn
:class:`ParseState`; no I/O, no SDK client — so the mapping is unit-testable on
canned SDK message objects.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, UserMessage
from claude_agent_sdk import TextBlock as SdkTextBlock
from claude_agent_sdk import ToolResultBlock as SdkToolResultBlock
from claude_agent_sdk import ToolUseBlock as SdkToolUseBlock

from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.infrastructure.chat.adapter_support import ParseState

_logger = logging.getLogger(__name__)


def map_sdk_message(msg: Any, state: ParseState) -> list[AgentEvent]:
    """Map one streamed SDK message to zero or more ``AgentEvent``s.

    Dispatches by SDK message type: ``SystemMessage(init)``
    captures the session id; ``AssistantMessage`` yields text/tool-call events;
    ``UserMessage`` carries tool results; ``ResultMessage`` is terminal.
    """
    if isinstance(msg, SystemMessage):
        if msg.subtype == "init":
            state.session_id = (msg.data or {}).get("session_id") or state.session_id
        return []
    if isinstance(msg, AssistantMessage):
        return _assistant_blocks(msg, state)
    if isinstance(msg, UserMessage):
        return _tool_results(msg, state)
    if isinstance(msg, ResultMessage):
        return _result(msg, state)
    return []


def _assistant_blocks(msg: AssistantMessage, state: ParseState) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    for block in msg.content:
        if isinstance(block, SdkTextBlock):
            if block.text:
                out.append(TextDelta(text=block.text))
        elif isinstance(block, SdkToolUseBlock):
            tid = str(block.id)
            name = str(block.name)
            state.tool_names[tid] = name
            out.append(ToolCall(tool_use_id=tid, tool_name=name, tool_input=block.input or {}))
    return out


def _tool_results(msg: UserMessage, state: ParseState) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    content = msg.content
    if not isinstance(content, list):
        return out
    for block in content:
        if not isinstance(block, SdkToolResultBlock):
            continue
        tid = str(block.tool_use_id)
        is_error = bool(block.is_error)
        text = _stringify(block.content)
        out.append(
            ToolResult(
                tool_use_id=tid,
                tool_name=state.tool_names.get(tid, ""),
                output=None if is_error else {"content": text},
                error=text if is_error else None,
            )
        )
    return out


def _result(msg: ResultMessage, state: ParseState) -> list[AgentEvent]:
    usage = msg.usage or {}
    state.prompt_tokens = usage.get("input_tokens")
    state.completion_tokens = usage.get("output_tokens")
    state.terminal_emitted = True
    if msg.is_error or msg.subtype not in (None, "success"):
        return [
            TurnError(
                code="sdk_error",
                message=str(msg.result or msg.subtype or "claude sdk error"),
            )
        ]
    if msg.subtype is None:
        _logger.warning(
            "claude_sdk_agent.result_subtype_none",
            extra={"session_id": state.session_id, "stop_reason": msg.stop_reason},
        )
    return [
        TurnDone(
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            stop_reason=str(msg.stop_reason or "end_turn"),
        )
    ]


def _stringify(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
        return "".join(parts)
    return str(content)


__all__ = ["map_sdk_message"]
