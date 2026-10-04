"""A reply is shaped for what the chat can show before it is delivered (spec
channels "Shape a reply for what the chat can show")."""

from __future__ import annotations

import asyncio
import pathlib
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


@pytest.mark.acceptance(
    spec="channels", scenario="a table's CSV and a long log follow the answer as files"
)
async def test_a_big_table_and_a_long_log_go_out_as_files_after_the_answer() -> None:
    adapter = FakeChannelAdapter(
        supports_edit=False, renders_tables=False, max_inline_code_lines=30
    )
    rows = "\n".join(f"| job{i} | ok |" for i in range(20))
    log = "\n".join(f"line {i}" for i in range(50))

    await _run(adapter, f"All green.\n\n| job | state |\n|---|---|\n{rows}\n\n```log\n{log}\n```")

    [answer] = adapter.texts()
    assert "- **job0** · ok" in answer and "|---|" not in answer
    assert "*… 20 rows in table-1.csv*" in answer
    assert "*… 50 lines in log-2.log*" in answer
    names = [pathlib.Path(path).name for _chat, path, _caption, _photo in adapter.media]
    assert names == ["table-1.csv", "log-2.log"]
    assert all(photo is False for *_rest, photo in adapter.media)


async def test_a_transport_that_shows_tables_gets_them_as_written() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    table = "| a | b |\n|---|---|\n| 1 | 2 |"

    await _run(adapter, table)

    assert adapter.texts() == [table]
    assert adapter.media == []
