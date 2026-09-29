"""The shared fake IM transport records what the core sends and replays taps."""

from __future__ import annotations

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import ChoiceButton, InboundCallback, InboundMessage
from tests.support.channel import FakeChannelAdapter


async def _ignore(_message: InboundMessage) -> None:
    return None


async def test_outbound_calls_are_recorded_with_their_routing(
    fake_channel_adapter: FakeChannelAdapter,
) -> None:
    adapter = fake_channel_adapter
    await adapter.start(AdapterCallbacks(on_message=_ignore))
    assert adapter.started
    first = await adapter.send_text("c1", "hi", thread_id="t9", chat_kind="group")
    card = await adapter.send_text(
        "c1", "pick", buttons=[ChoiceButton(label="A", value="a")], title="Model"
    )
    await adapter.send_typing("c1")
    assert (first.message_id, card.message_id) == ("m1", "m2")
    assert adapter.texts() == ["hi", "pick"]
    assert adapter.sent_routed[0] == ("c1", "hi", "t9", "group")
    assert adapter.card_titles == ["Model"] and adapter.cards[0][2][0].value == "a"
    assert adapter.typing == ["c1"]
    await adapter.stop()
    assert adapter.stopped and not adapter.started


async def test_live_text_edits_in_place_then_hands_back_the_final_text() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)
    live = await adapter.open_live_text("c1")
    assert live is not None
    await live.update("Hel")
    await live.update("Hello")
    final = await live.close("Hello world")
    assert final == "Hello world"
    assert adapter.sent == [("c1", "Hel")]
    assert adapter.edits == [("c1", "m1", "Hello")]
    assert adapter.deleted == [("c1", "m1")]
    assert await FakeChannelAdapter(supports_edit=False).open_live_text("c1") is None


async def test_tap_delivers_a_callback_to_the_core() -> None:
    taps: list[InboundCallback] = []

    async def on_callback(event: InboundCallback) -> None:
        taps.append(event)

    adapter = FakeChannelAdapter(supports_buttons=True)
    await adapter.start(AdapterCallbacks(on_message=_ignore, on_callback=on_callback))
    await adapter.tap("model:fable", channel="im", chat_id="c7", sender_id="u1")
    assert [(t.channel, t.chat_id, t.sender_id, t.data) for t in taps] == [
        ("im", "c7", "u1", "model:fable")
    ]
