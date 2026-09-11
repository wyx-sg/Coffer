"""Map streamed Claude Agent SDK messages to ``AgentEvent``s.

Extracted from :mod:`claude_sdk_agent` (the file grew past its size budget). The
Codex analog is :mod:`codex_mapping`. Pure functions over a per-turn
:class:`ClaudeParseState`; no I/O, no SDK client — so the mapping is
unit-testable on canned SDK message objects.

The turn is streamed twice over: ``include_partial_messages`` makes the SDK emit
raw Anthropic ``StreamEvent``s as the reply is written, then deliver the finished
``AssistantMessage``. Both are mapped, and the state remembers what already went
out so the reply is never sent twice (see :class:`ClaudeParseState`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    UserMessage,
)
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


@dataclass
class ClaudeParseState(ParseState):
    """``ParseState`` plus the accumulator that keeps the reply from doubling.

    With ``include_partial_messages`` the SDK emits ``StreamEvent``s carrying the
    reply's text increments *and* still delivers the complete ``AssistantMessage``
    afterwards. Consumers concatenate ``TextDelta`` payloads, so what already
    streamed is remembered here and subtracted from the finished message.

    It is remembered as an ordered SEQUENCE — one entry per run of stream events
    that produced text — and the finished message's Nth text block is matched
    against the Nth entry. Not by content-block index: the SDK's message parser
    matches on block type with no fallback case, so a block type it does not
    recognise (``redacted_thinking``, or anything Anthropic adds later) is
    silently dropped rather than appended, and every later block's position in
    the parsed content then sits below its raw stream index. Relative order,
    unlike position, survives any number of dropped blocks.
    """

    #: Text streamed so far for the assistant message currently being received,
    #: one entry per content block that produced text, in the order they were
    #: streamed. Cleared once that message has been mapped.
    stream_text: list[str] = field(default_factory=list)
    #: The raw stream index the last text increment belonged to, so increments of
    #: one block extend its entry while a new block opens the next one.
    stream_index: int | None = None


def map_sdk_message(msg: Any, state: ClaudeParseState) -> list[AgentEvent]:
    """Map one streamed SDK message to zero or more ``AgentEvent``s.

    Dispatches by SDK message type: ``SystemMessage(init)``
    captures the session id; ``StreamEvent`` yields the incremental text deltas;
    ``AssistantMessage`` yields the remaining text plus tool-call events;
    ``UserMessage`` carries tool results; ``ResultMessage`` is terminal.
    """
    if isinstance(msg, SystemMessage):
        if msg.subtype == "init":
            state.session_id = (msg.data or {}).get("session_id") or state.session_id
        return []
    if isinstance(msg, StreamEvent):
        return _stream_event(msg, state)
    if isinstance(msg, AssistantMessage):
        return _assistant_blocks(msg, state)
    if isinstance(msg, UserMessage):
        return _tool_results(msg, state)
    if isinstance(msg, ResultMessage):
        return _result(msg, state)
    return []


def _stream_event(msg: StreamEvent, state: ClaudeParseState) -> list[AgentEvent]:
    """Relay one raw Anthropic stream event as an incremental ``TextDelta``.

    Only text increments are text a reader sees, so everything else — thinking
    deltas, a tool call's ``input_json_delta``, the message/content-block
    envelopes — maps to nothing. Sub-agent events (``parent_tool_use_id`` set)
    are skipped too: their text is not part of this message, and letting it into
    the accumulator would corrupt the de-duplication below.
    """
    if msg.parent_tool_use_id is not None:
        return []
    event = msg.event or {}
    if event.get("type") != "content_block_delta":
        return []
    delta = event.get("delta") or {}
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
        return []
    text = str(delta.get("text") or "")
    if not text:
        return []
    raw_index = event.get("index")
    index = raw_index if isinstance(raw_index, int) else 0
    if state.stream_index == index and state.stream_text:
        state.stream_text[-1] += text
    else:
        # A new content block is streaming: open the next entry. The index is
        # only read to tell one block's run of increments from the next one's —
        # never used to address a block in the finished message.
        state.stream_text.append(text)
        state.stream_index = index
    return [TextDelta(text=text)]


def _undelivered_text(full: str, streamed: str) -> str:
    """The part of a finished text block a consumer has not been sent yet."""
    if not streamed:
        # No partial messages arrived (an older CLI, or a turn with no text
        # increments): the whole block is new — the pre-streaming behaviour.
        return full
    if full.startswith(streamed):
        # Everything streamed (usually all of it), or all but a late remainder.
        return full[len(streamed) :]
    # The stream and the finished block disagree. The reader has already seen
    # the streamed text, so emit nothing rather than send the reply twice.
    _logger.warning(
        "claude_sdk_mapping.stream_text_mismatch",
        extra={"streamed_chars": len(streamed), "block_chars": len(full)},
    )
    return ""


def _assistant_blocks(msg: AssistantMessage, state: ClaudeParseState) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    # Text blocks and streamed entries are both in order, so walking the entries
    # once alongside the blocks pairs them up. An exhausted iterator yields "",
    # which is exactly the "nothing streamed for this block" case.
    streamed = iter(state.stream_text)
    for block in msg.content:
        if isinstance(block, SdkTextBlock):
            text = _undelivered_text(block.text, next(streamed, ""))
            if text:
                out.append(TextDelta(text=text))
        elif isinstance(block, SdkToolUseBlock):
            tid = str(block.id)
            name = str(block.name)
            state.tool_names[tid] = name
            out.append(ToolCall(tool_use_id=tid, tool_name=name, tool_input=block.input or {}))
    # The accumulator is per assistant message: a turn that runs a tool between
    # two messages must not measure the second against the first's text.
    state.stream_text.clear()
    state.stream_index = None
    return out


def _tool_results(msg: UserMessage, state: ClaudeParseState) -> list[AgentEvent]:
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


def _result(msg: ResultMessage, state: ClaudeParseState) -> list[AgentEvent]:
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


__all__ = ["ClaudeParseState", "map_sdk_message"]
