"""A reply's details behind a summary card (spec channels "Offer a reply's
details behind a summary card")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.channel.details_card import load_details
from coffer.domain.chat.events import TextDelta, TurnDone, TurnStarted
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, wait_until

_REPLY = "Deploy is green on live.\n\n## Details\n\n- built in 3m\n- 412 tests passed"
_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _seatalk_like(**kwargs: object) -> FakeChannelAdapter:
    return FakeChannelAdapter(
        supports_edit=False,
        supports_buttons=True,
        supports_card_update=True,
        direct_threads_are_replies=True,
        **kwargs,  # type: ignore[arg-type]
    )


async def _answered(env: ChannelEnv, adapter: FakeChannelAdapter) -> str:
    env.provider.adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text=_REPLY), _DONE])
    resource = await env.register_channel()
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.processor.on_message(inbound("tg", "owner", "deploy?", sender_id="owner-1"))
    await wait_until(lambda: bool(adapter.cards))
    [(_chat, _text, buttons)] = adapter.cards
    return buttons[0].value.split(":", 1)[1]


@pytest.mark.acceptance(
    spec="channels", scenario="details go behind a card where the chat cannot collapse them"
)
async def test_the_answer_head_is_sent_and_its_details_go_behind_a_card(env: ChannelEnv) -> None:
    adapter = _seatalk_like()

    details_id = await _answered(env, adapter)

    assert "Deploy is green on live." in adapter.texts()
    assert not any("412 tests" in t for t in adapter.texts() if t != adapter.cards[0][1])
    [(_chat, text, buttons)] = adapter.cards
    assert adapter.card_titles == ["Deploy is green on live."]
    assert text == "2 more lines of details."
    assert [b.label for b in buttons] == ["Details", "As file"]
    assert load_details(details_id) == "## Details\n\n- built in 3m\n- 412 tests passed"


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="the details button posts them as a thread reply"
)
async def test_details_are_posted_as_a_reply_in_the_cards_thread(env: ChannelEnv) -> None:
    adapter = _seatalk_like()
    details_id = await _answered(env, adapter)

    await env.processor.on_callback(
        tap_event(
            "tg", "owner", f"details:{details_id}", sender_id="owner-1", platform_message_id="m7"
        )
    )

    posted = [r for r in adapter.sent_routed if "412 tests passed" in r[1]]
    assert posted and posted[-1][2] == "m7"  # a reply in the thread the card roots
    assert adapter.card_updates[-1][2] == "Details posted in the thread."


async def test_as_file_uploads_the_details_as_markdown(env: ChannelEnv) -> None:
    adapter = _seatalk_like()
    details_id = await _answered(env, adapter)

    await env.processor.on_callback(
        tap_event(
            "tg",
            "owner",
            f"detailsfile:{details_id}",
            sender_id="owner-1",
            platform_message_id="m7",
        )
    )

    [(_chat, path, _caption, as_photo)] = adapter.media
    assert pathlib.Path(path).suffix == ".md" and as_photo is False


async def test_a_details_id_that_is_gone_says_so(env: ChannelEnv) -> None:
    adapter = _seatalk_like()
    await _answered(env, adapter)

    await env.processor.on_callback(
        tap_event("tg", "owner", "details:0123456789abcdef", sender_id="owner-1")
    )

    assert any("no longer available" in t for t in adapter.texts())


async def test_a_transport_that_collapses_details_sends_no_card(env: ChannelEnv) -> None:
    adapter = _seatalk_like(collapses_details=True)
    env.provider.adapter = FakeAgentAdapter([TurnStarted(), TextDelta(text=_REPLY), _DONE])
    resource = await env.register_channel()
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(inbound("tg", "owner", "deploy?", sender_id="owner-1"))
    await wait_until(lambda: any("412 tests" in t for t in adapter.texts()))

    assert adapter.cards == []
