"""A finished reply goes out as the agent wrote it: Coffer does not rewrite
tables or move code blocks into files (spec channels "Shape a reply for what
the chat can show")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, TurnDone

from .conftest import FakeChannelAdapter

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


async def _run(adapter: FakeChannelAdapter, text: str) -> None:
    async def send(body: str) -> None:
        await adapter.send_text("owner", body)

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        now=lambda: 0.0,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [TextDelta(text=text), _DONE, None]:
        queue.put_nowait(event)
    await renderer.consume(queue)


@pytest.mark.acceptance(spec="channels", scenario="a table goes out as the agent wrote it")
async def test_a_table_goes_out_as_the_agent_wrote_it() -> None:
    adapter = FakeChannelAdapter()
    table = "| a | b |\n|---|---|\n| 1 | 2 |"

    await _run(adapter, table)

    assert adapter.texts() == [table]
    assert adapter.media == []
