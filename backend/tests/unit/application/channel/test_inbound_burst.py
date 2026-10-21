"""The inbound burst buffer (spec channels "Take a burst of messages as one turn")."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel import inbound_burst
from coffer.application.channel.inbound_burst import BurstPart, InboundBurst, merge_parts
from coffer.application.channel.turn_driver import QueuedInbound
from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.channel.turn_content import ContextBlock, MessageContent
from coffer.domain.chat.attachment import Attachment

KEY = ("chan", "chat", "")


@pytest.fixture(autouse=True)
def _real_window_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite-wide conftest caps windows at 0; these tests are about windows.
    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 60.0)


def _part(
    body: str,
    *,
    msg_id: str = "",
    window: float = 0.02,
    content: MessageContent | None = None,
    **item: Any,
) -> BurstPart:
    return BurstPart(
        origin=f"[origin {msg_id}]",
        content=content or MessageContent(text=body),
        item=QueuedInbound(text="", reply_to_message_id=msg_id, **item),
        window=window,
    )


def _user(text: str, tag: str = "") -> str:
    return f"[User message{tag}]\n{text}\n[End of user message]"


def _collector() -> tuple[list[QueuedInbound], Any]:
    released: list[QueuedInbound] = []

    async def on_flush(_context: Any, merged: QueuedInbound) -> None:
        released.append(merged)

    return released, on_flush


@pytest.mark.acceptance(
    spec="channels", scenario="a burst of several messages keeps each one apart"
)
def test_merge_keeps_one_origin_every_message_and_numbers_every_attachment() -> None:
    chart = InboundAttachment(path="/m/chart.png", mime="image/png", filename="chart.png", ref="u1")
    photo = InboundAttachment(path="/m/photo.png", mime="image/png", filename="photo.png")
    record = MessageContent(
        blocks=(
            ContextBlock(
                kind="forwarded",
                items=(
                    ForwardedItem("xingz@sea.com", "see the chart"),
                    ForwardedItem(
                        "xingz@sea.com", "[image] u1", media_ref="u1", media_label="[image]"
                    ),
                ),
                media=(chart,),
            ),
        )
    )
    merged = merge_parts(
        [
            _part("", msg_id="m1", content=record, window=0.08),
            _part("look into this", msg_id="m2", title_hint="look into this"),
            _part("", msg_id="m3", content=MessageContent(media=(photo,))),
        ]
    )
    assert merged.text == (
        "[origin m3]\n\n"
        "[Forwarded chat record — forwarded by the user; written by others]\n"
        "xingz@sea.com: see the chart\n"
        "xingz@sea.com: [image] → attachment #1\n"
        "[End of forwarded chat record]\n\n"
        f"{_user('look into this', ' 1/2')}\n\n"
        f"{_user('(sent an image → attachment #2)', ' 2/2')}"
    )
    assert merged.attachments == (
        Attachment("/m/chart.png", "image/png", "chart.png", 1, "the forwarded record"),
        Attachment("/m/photo.png", "image/png", "photo.png", 2, "the user's message 2/2"),
    )
    assert merged.reply_to_message_id == "m3"
    assert merged.title_hint == "look into this"


async def test_a_message_inside_the_window_joins_the_burst() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("record", msg_id="m1", window=0.08))
    assert released == []  # still held: the long window has not run out
    burst.add(KEY, None, _part("look into this", msg_id="m2"))
    await burst.settled()
    assert len(released) == 1
    assert released[0].text.endswith(
        f"{_user('record', ' 1/2')}\n\n{_user('look into this', ' 2/2')}"
    )


async def test_messages_further_apart_than_the_window_are_separate() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("one", msg_id="m1"))
    await burst.settled()  # the window ran out before the next message
    burst.add(KEY, None, _part("two", msg_id="m2"))
    await burst.settled()
    assert [r.text for r in released] == [
        f"[origin m1]\n\n{_user('one')}",
        f"[origin m2]\n\n{_user('two')}",
    ]


async def test_other_keys_do_not_merge() -> None:
    released, on_flush = _collector()
    burst = InboundBurst(on_flush)
    burst.add(KEY, None, _part("dm"))
    burst.add(("chan", "chat", "t1"), None, _part("thread"))
    await burst.settled()
    assert sorted(r.text.split("\n\n")[1] for r in released) == [_user("dm"), _user("thread")]


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
