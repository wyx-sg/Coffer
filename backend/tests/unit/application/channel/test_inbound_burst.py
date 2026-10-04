"""The inbound burst buffer (spec channels "Take a burst of messages as one turn")."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel import inbound_burst
from coffer.application.channel.inbound_burst import BurstPart, InboundBurst, merge_parts
from coffer.application.channel.turn_driver import QueuedInbound
from coffer.domain.chat.attachment import Attachment

KEY = ("chan", "chat", "")


@pytest.fixture(autouse=True)
def _real_window_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite-wide conftest caps windows at 0; these tests are about windows.
    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 60.0)


def _part(body: str, *, msg_id: str = "", window: float = 0.02, **item: Any) -> BurstPart:
    return BurstPart(
        origin=f"[origin {msg_id}]",
        body=body,
        item=QueuedInbound(text="", reply_to_message_id=msg_id, **item),
        window=window,
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
            _part("record", msg_id="m1", attachments=(a,), window=0.08),
            _part("look into this", msg_id="m2", title_hint="look into this"),
        ]
    )
    assert merged.text == "[origin m2]\n\nrecord\n\nlook into this"
    assert merged.attachments == (a,)
    assert merged.reply_to_message_id == "m2"
    assert merged.title_hint == "look into this"


async def test_a_message_inside_the_window_joins_the_burst() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("record", msg_id="m1", window=0.08))
    assert released == []  # still held: the long window has not run out
    burst.add(KEY, None, _part("look into this", msg_id="m2"))
    await burst.settled()
    assert len(released) == 1
    assert released[0].text.endswith("record\n\nlook into this")


async def test_messages_further_apart_than_the_window_are_separate() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("one", msg_id="m1"))
    await burst.settled()  # the window ran out before the next message
    burst.add(KEY, None, _part("two", msg_id="m2"))
    await burst.settled()
    assert [r.text for r in released] == ["[origin m1]\n\none", "[origin m2]\n\ntwo"]


async def test_other_keys_do_not_merge() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("dm"))
    burst.add(("chan", "chat", "t1"), None, _part("thread"))
    await burst.settled()
    assert sorted(r.text.split("\n\n")[1] for r in released) == ["dm", "thread"]


async def test_flush_releases_now_and_awaits_the_submission() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("held", window=10))
    await burst.flush(KEY)
    assert len(released) == 1
    assert not burst.holding(KEY)


async def test_drop_discards_the_burst() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("never"))
    await burst.drop(KEY)
    await burst.settled()
    assert released == []
    assert not burst.holding(KEY)
