"""Unit-ish tests for the LangGraph → AgentEvent stream mapper.

``map_graph_stream`` is a pure async generator over a LangGraph
``["messages", "updates"]`` stream, so we drive it with a hand-built fake
stream rather than a real graph. Lives under integration/ because it imports
``langchain_core`` message types (Contract 9 boundary).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from coffer.domain.chat.events import TextDelta, TurnDone
from coffer.infrastructure.chat._event_mapping import map_graph_stream


async def _stream(items: list[tuple[str, Any]]) -> AsyncIterator[tuple[str, Any]]:
    for item in items:
        yield item


async def _collect(items: list[tuple[str, Any]]) -> list[Any]:
    return [ev async for ev in map_graph_stream(_stream(items))]


@pytest.mark.asyncio
async def test_messages_mode_list_content_chunk_streams_text() -> None:
    """An AIMessageChunk whose content is Anthropic-style multi-part list must
    still stream as TextDelta tokens (not be dropped until the final update)."""
    chunk = AIMessageChunk(
        id="m1",
        content=[{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
    )
    items = [("messages", (chunk, {"langgraph_node": "agent"}))]

    events = await _collect(items)

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "hello world"


@pytest.mark.asyncio
async def test_updates_mode_tolerates_text_part_without_text_key() -> None:
    """A text-typed content part missing its 'text' key must be skipped in
    updates mode (same tolerance as _chunk_text), not raise KeyError."""
    msg = AIMessage(
        id="a1",
        content=[{"type": "text"}, {"type": "text", "text": "kept"}],
    )
    items = [("updates", {"agent": {"messages": [msg]}})]

    events = await _collect(items)  # must not raise

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "kept"


@pytest.mark.asyncio
async def test_token_usage_is_summed_across_agent_calls() -> None:
    """A multi-call turn (tool loop) records the sum of every LLM call's usage,
    not just the last call's."""
    first = AIMessage(
        id="a1",
        content="",
        usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
    )
    second = AIMessage(
        id="a2",
        content="final",
        usage_metadata={"input_tokens": 20, "output_tokens": 6, "total_tokens": 26},
    )
    items = [
        ("updates", {"agent": {"messages": [first]}}),
        ("updates", {"agent": {"messages": [second]}}),
    ]

    events = await _collect(items)

    done = next(e for e in events if isinstance(e, TurnDone))
    assert done.prompt_tokens == 30  # 10 + 20
    assert done.completion_tokens == 10  # 4 + 6
