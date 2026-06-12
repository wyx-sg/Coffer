"""Map LangGraph ``astream`` events to Coffer ``AgentEvent``s.

This module is imported only by ``langgraph_agent.py`` and is therefore
confined to ``coffer.infrastructure.chat`` (Contract 9).

We use ``stream_mode=["messages", "updates"]``:

- ``messages`` events (``AIMessageChunk``) carry streaming text tokens.
- ``updates`` events carry node-level completions:
  - ``agent`` node → ``AIMessage`` with ``tool_calls`` list: emit ``ToolCall``s.
  - ``tools`` node → ``ToolMessage`` per tool: emit ``ToolResult``.
  - ``agent`` node → final ``AIMessage`` with content and ``usage_metadata``:
    provides token counts for ``TurnDone``.

Text deduplication: text is streamed token-by-token via ``messages`` mode and
accumulated; the final ``AIMessage`` content in ``updates`` mode is ignored for
text (we already streamed those tokens).  Only the ``usage_metadata`` from the
final update is used.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def map_graph_stream(
    stream: AsyncIterator[Any],
) -> AsyncIterator[Any]:
    """Consume a LangGraph ``["messages", "updates"]`` stream and yield
    ``AgentEvent``s.

    Yields ``TurnDone`` as the *last* event on normal completion.
    Raises on ``GraphRecursionError`` or other LangGraph errors; the caller
    (``LangGraphBuiltinAgent._stream``) wraps those in ``TurnError``.
    """
    # Deferred import — this module lives inside infrastructure/chat.
    from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

    from coffer.domain.chat.events import (
        TextDelta,
        ToolCall,
        ToolResult,
        TurnDone,
    )

    # Track per-tool-call IDs to associate ToolResult with its call.
    # Maps call_id → tool_name
    pending_calls: dict[str, str] = {}

    # Accumulate token usage from the last agent update.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    stop_reason = "end_turn"

    # Track whether we've emitted any TextDelta for the current agent turn
    # to avoid double-emitting text from both messages and updates modes.
    emitted_message_ids: set[str] = set()

    async for mode, data in stream:
        if mode == "messages":
            # data is (chunk, metadata)
            chunk, metadata = data
            node = metadata.get("langgraph_node", "")
            if node != "agent":
                # We only care about agent text deltas; tool results come
                # from updates mode.
                continue

            if isinstance(chunk, AIMessageChunk):
                # Track by message id to avoid duplicating text when the same
                # message surfaces in both messages and updates.
                msg_id = chunk.id or ""

                # Recent langchain-anthropic streams content as either a plain
                # ``str`` or a list of content-block dicts; handle both so
                # Anthropic streams token-by-token instead of popping the whole
                # answer only when the final update arrives.
                text = _chunk_text(chunk.content)
                if text:
                    # Only track in dedup set when the id is non-empty; adding ""
                    # would mute all later id-less updates from this stream.
                    if msg_id:
                        emitted_message_ids.add(msg_id)
                    yield TextDelta(text=text)

        elif mode == "updates":
            # data is a dict: {node_name: {"messages": [...]}}
            for node_name, node_data in data.items():
                if not isinstance(node_data, dict):
                    continue

                messages = node_data.get("messages", [])
                if not isinstance(messages, list):
                    continue

                for msg in messages:
                    if node_name == "agent":
                        if isinstance(msg, AIMessage):
                            # Register tool calls
                            for tc in msg.tool_calls or []:
                                call_id = tc.get("id") or ""
                                tool_name = tc.get("name") or ""
                                pending_calls[call_id] = tool_name
                                yield ToolCall(
                                    tool_use_id=call_id,
                                    tool_name=tool_name,
                                    tool_input=dict(tc.get("args") or {}),
                                )

                            # Sum usage across every LLM call in the turn (a
                            # tool loop makes several); each call is billed
                            # separately, so the turn's cost is the total.
                            usage = getattr(msg, "usage_metadata", None)
                            if usage:
                                in_toks = usage.get("input_tokens")
                                out_toks = usage.get("output_tokens")
                                if in_toks is not None:
                                    prompt_tokens = (prompt_tokens or 0) + in_toks
                                if out_toks is not None:
                                    completion_tokens = (completion_tokens or 0) + out_toks

                            # Emit text from updates only if we didn't already
                            # stream it via messages mode. _chunk_text handles
                            # both str and Anthropic-style list content — one
                            # parser for both stream modes.
                            msg_id = msg.id or ""
                            if msg.content and msg_id not in emitted_message_ids:
                                text = _chunk_text(msg.content)
                                if text:
                                    # Only update dedup bookkeeping when id is
                                    # non-empty.
                                    if msg_id:
                                        emitted_message_ids.add(msg_id)
                                    yield TextDelta(text=text)

                    elif node_name == "tools" and isinstance(msg, ToolMessage):
                        call_id = msg.tool_call_id or ""
                        tool_name = pending_calls.get(call_id, msg.name or "")
                        is_error = getattr(msg, "status", "success") == "error"
                        raw_content = msg.content
                        if isinstance(raw_content, str):
                            output_dict: dict[str, Any] | None
                            error_str: str | None
                            if is_error:
                                output_dict = None
                                error_str = raw_content
                            else:
                                output_dict = {"result": raw_content}
                                error_str = None
                        elif isinstance(raw_content, dict):
                            output_dict = raw_content if not is_error else None
                            error_str = str(raw_content) if is_error else None
                        else:
                            output_dict = {"result": str(raw_content)}
                            error_str = None
                        yield ToolResult(
                            tool_use_id=call_id,
                            tool_name=tool_name,
                            output=output_dict,
                            error=error_str,
                        )

    yield TurnDone(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        stop_reason=stop_reason,
    )


def _chunk_text(content: Any) -> str:
    """Extract streamed text from an ``AIMessageChunk.content``.

    Content is either a plain ``str`` or a list of content-block dicts
    (Anthropic multi-part). Non-text parts are ignored.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part["text"]
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and "text" in part
        )
    return ""
