"""The inbound burst buffer (spec channels "Take a burst of messages as one turn")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.inbound_burst import BurstPart, InboundBurst, merge_parts
from coffer.application.channel.turn_driver import QueuedInbound
from coffer.domain.chat.attachment import Attachment

KEY = ("chan", "chat", "")


def _part(body: str, *, msg_id: str = "", wants_more: bool = False, **item: Any) -> BurstPart:
    return BurstPart(
        origin=f"[origin {msg_id}]",
        body=body,
        item=QueuedInbound(text="", reply_to_message_id=msg_id, **item),
        wants_more=wants_more,
    )


def _collector() -> tuple[list[QueuedInbound], Any]:
    released: list[QueuedInbound] = []

    async def on_flush(_context: Any, merged: QueuedInbound) -> None:
        released.append(merged)

    return released, on_flush


def test_merge_keeps_one_origin_every_body_and_every_attachment() -> None:
    a = Attachment(path="/tmp/a.png", mime="image/png", filename="a.png")
    merged = merge_parts(
        [
            _part("record", msg_id="m1", attachments=(a,), wants_more=True),
            _part("look into this", msg_id="m2", title_hint="look into this"),
        ]
    )
    assert merged.text == "[origin m2]\n\nrecord\n\nlook into this"
    assert merged.attachments == (a,)
    assert merged.reply_to_message_id == "m2"
    assert merged.title_hint == "look into this"


@pytest.mark.acceptance(
    spec="channels", scenario="a forwarded record and its follow-up become one turn"
)
async def test_a_message_inside_the_window_joins_the_burst() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush, short_window=0.02, long_window=0.08)
    burst.add(KEY, None, _part("record", msg_id="m1", wants_more=True))
    await asyncio.sleep(0.04)  # inside the long window
    assert released == []
    burst.add(KEY, None, _part("look into this", msg_id="m2"))
    await asyncio.sleep(0.06)
    assert len(released) == 1
    assert released[0].text.endswith("record\n\nlook into this")


@pytest.mark.acceptance(
    spec="channels", scenario="messages further apart than the window are separate turns"
)
async def test_messages_further_apart_than_the_window_are_separate() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush, short_window=0.02, long_window=0.08)
    burst.add(KEY, None, _part("one", msg_id="m1"))
    await asyncio.sleep(0.05)
    burst.add(KEY, None, _part("two", msg_id="m2"))
    await asyncio.sleep(0.05)
    assert [r.text for r in released] == ["[origin m1]\n\none", "[origin m2]\n\ntwo"]


async def test_other_keys_do_not_merge() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush, short_window=0.02, long_window=0.08)
    burst.add(KEY, None, _part("dm"))
    burst.add(("chan", "chat", "t1"), None, _part("thread"))
    await asyncio.sleep(0.05)
    assert sorted(r.text.split("\n\n")[1] for r in released) == ["dm", "thread"]


async def test_flush_releases_now_and_awaits_the_submission() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush, short_window=10, long_window=10)
    burst.add(KEY, None, _part("held"))
    await burst.flush(KEY)
    assert len(released) == 1
    assert not burst.holding(KEY)


@pytest.mark.acceptance(spec="channels", scenario="/stop drops messages still being held")
async def test_drop_discards_the_burst() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush, short_window=0.02, long_window=0.02)
    burst.add(KEY, None, _part("never"))
    await burst.drop(KEY)
    await asyncio.sleep(0.05)
    assert released == []
