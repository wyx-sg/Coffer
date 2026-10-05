"""A SeaTalk stream is written by one writer, newest snapshot first.

Spec channels/seatalk "Stream the reply under SeaTalk's streaming contract": the
client renders the latest snapshot it receives, so a write that carries an older
snapshot than the one already on screen makes the message jump back and then
forward again. Three callers offer snapshots — the turn's event loop, the status
tick and the surface's keep-alive — and these tests record every payload the
platform is sent, in order, with a deliberately slow platform so writes overlap.
"""

from __future__ import annotations

import asyncio
import itertools
import random
from dataclasses import replace
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.application.channel.turn_status import LIVE_SEPARATOR
from coffer.domain.chat.events import TextDelta, TurnDone
from coffer.infrastructure.channel.seatalk_caps import SEATALK_CAPABILITIES
from coffer.infrastructure.channel.seatalk_live import SeaTalkLiveText

from .conftest import wait_until

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


class SlowSeaTalk:
    """Records every stream payload in the order the platform receives it, with
    a latency per request, and how many requests were ever in flight at once."""

    def __init__(self, latency: Any = 0.0) -> None:
        self._latency = latency
        self.calls: list[dict[str, Any]] = []  # arrival order
        self.in_flight = 0
        self.max_in_flight = 0
        self.gate: asyncio.Event | None = None  # holds the next update open

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            delay = self._latency() if callable(self._latency) else self._latency
            await asyncio.sleep(delay)
            if path.endswith("update_stream") and self.gate is not None:
                gate, self.gate = self.gate, None
                await gate.wait()
        finally:
            self.in_flight -= 1
        if path.endswith("init_stream"):
            self.calls.append({"seq": 0, "content": body["message"]["text"]["content"]})
            return {"stream_id": "s1"}
        self.calls.append(
            {"seq": body["seq"], "content": body["message"]["text"]["content"], **body}
        )
        return {}

    @property
    def interim(self) -> list[str]:
        return [c["content"] for c in self.calls if not c.get("finish")]


def _answer(snapshot: str) -> str:
    rule = f"\n{LIVE_SEPARATOR}\n"
    return snapshot.split(rule, 1)[1] if rule in snapshot else ""


async def test_a_keepalive_during_an_update_in_flight_never_resends_an_older_snapshot() -> None:
    platform = SlowSeaTalk()
    live = SeaTalkLiveText(platform.post, "emp-1", keepalive_seconds=0.02)
    live._min_interval = 0.0  # every offer is due at once; the race is what is tested
    await live.update("I found")  # init_stream
    await asyncio.sleep(0.03)  # past one keep-alive interval: the surface is idle
    gate = platform.gate = asyncio.Event()
    # This update hangs at the platform while several keep-alive intervals pass.
    pending = asyncio.create_task(live.update("I found three"))
    await asyncio.sleep(0.1)
    gate.set()
    await pending
    await wait_until(lambda: platform.in_flight == 0)
    await live.close("I found three cats.")

    assert platform.max_in_flight == 1
    assert [c["seq"] for c in platform.calls] == list(range(len(platform.calls)))
    # Once "I found three" was sent, nothing older follows it.
    after = platform.interim[platform.interim.index("I found three") :]
    assert set(after) == {"I found three"}


async def test_an_offer_inside_the_buffer_is_written_when_the_buffer_ends() -> None:
    platform = SlowSeaTalk()
    live = SeaTalkLiveText(platform.post, "emp-1", keepalive_seconds=60.0)
    await live.update("I found")
    await live.update("I found three")  # inside the buffer: kept, not dropped

    await wait_until(lambda: "I found three" in platform.interim, timeout=2.0)
    await live.close("I found three cats.")


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a seatalk stream never shows an older snapshot after a newer one",
)
async def test_a_streamed_turn_is_written_in_order_and_never_goes_back() -> None:
    """The whole path — renderer, status tick, keep-alive, SeaTalk surface —
    against a platform slower than the buffer interval, so every writer overlaps
    with every other."""
    rng = random.Random(7)
    platform = SlowSeaTalk(latency=lambda: rng.uniform(0.005, 0.03))

    class Adapter:
        capabilities = replace(SEATALK_CAPABILITIES, supports_typing=False, supports_media=False)

        async def open_live_text(self, chat_id: str, **_kw: Any) -> SeaTalkLiveText:
            live = SeaTalkLiveText(platform.post, chat_id, keepalive_seconds=0.05)
            live._min_interval = 0.01
            return live

        async def send_text(self, *_a: Any, **_kw: Any) -> None:
            return None

    async def send(_text: str) -> None:
        return None

    renderer = TurnRenderer(
        channel="st",
        adapter=Adapter(),  # type: ignore[arg-type]
        chat_id="emp-1",
        conversation_id="c-order",
        send=send,
        tick_seconds=0.05,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    task = asyncio.create_task(renderer.consume(queue))
    for i in range(120):
        await queue.put(TextDelta(text=f"w{i} "))
        await asyncio.sleep(0.003)
    await queue.put(_DONE)
    await queue.put(None)
    await task

    assert platform.max_in_flight == 1
    assert [c["seq"] for c in platform.calls] == list(range(len(platform.calls)))
    assert platform.calls[-1]["finish"] is True
    answers = [_answer(s) for s in platform.interim]
    for older, newer in itertools.pairwise(answers):
        assert newer.startswith(older), (older, newer)
    headers = [s.split("\n", 1)[0] for s in platform.interim]
    seconds = [int(h.split("· ")[1].rstrip("s")) for h in headers]
    assert seconds == sorted(seconds)
