"""`/resume` reopens an earlier conversation of this chat thread (spec channels
"Resume an earlier conversation from chat")."""

from __future__ import annotations

import pytest

from coffer.application.channel.resume_switch import NOTHING_TO_RESUME
from coffer.domain.channel.envelopes import ChoiceButton

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event


async def _card_channel(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner")
    return resource, adapter


async def _three_conversations(env: ChannelEnv, resource: Resource) -> list[str]:
    """Open three conversations in the DM, titled one, two, three (oldest first)."""
    ids = []
    for title in ("one", "two", "three"):
        await env.processor.on_message(inbound("tg", "owner", "/new"))
        conversation_id = await env.active_conversation(resource)
        assert conversation_id is not None
        await env.chat.rename_conversation(conversation_id, new_title=title)
        ids.append(conversation_id)
    return ids


@pytest.mark.acceptance(spec="channels", scenario="/resume lists this chat's earlier conversations")
async def test_resume_lists_this_chats_earlier_conversations(env: ChannelEnv) -> None:
    env.add_agent("codex")
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/resume"))
    assert adapter.texts() == [NOTHING_TO_RESUME]
    ids = await _three_conversations(env, resource)
    # A conversation deleted since is skipped.
    await env.chat.delete_conversation(ids[0])

    await env.processor.on_message(inbound("tg", "owner", "/resume"))

    lines = adapter.texts()[-1].splitlines()
    assert lines[0] == "Resume a conversation"
    assert lines[1] == "Send /resume <n> to reopen one:"
    assert lines[2] == "1 · three — Coffer Assistant · just now ✓"
    assert lines[3] == "2 · two — Coffer Assistant · just now"
    assert len(lines) == 4  # title, hint, two conversations
    assert not any(conversation_id in adapter.texts()[-1] for conversation_id in ids)


def _resume_cards(adapter: FakeChannelAdapter) -> list[tuple[str, str, list[ChoiceButton]]]:
    """The `/resume` cards sent — each `/new` along the way answers with a card too."""
    return [
        c
        for c, title in zip(adapter.cards, adapter.card_titles, strict=True)
        if title == "Resume a conversation"
    ]


async def test_resume_is_a_card_where_the_transport_takes_one(env: ChannelEnv) -> None:
    resource, adapter = await _card_channel(env)
    ids = await _three_conversations(env, resource)

    await env.processor.on_message(inbound("tg", "owner", "/resume"))

    [(_chat, _text, buttons)] = _resume_cards(adapter)
    assert [b.value for b in buttons] == [f"resume:{i}" for i in reversed(ids)]
    assert buttons[0].label == "✓ 1"

    await env.processor.on_callback(
        tap_event("tg", "owner", f"resume:{ids[0]}", platform_message_id="c-1")
    )

    assert await env.active_conversation(resource) == ids[0]
    assert adapter.texts()[-1] == "↩️ Resumed \u201cone\u201d with Coffer Assistant."
    _chat, _mid, _text, buttons, _title = adapter.card_updates[-1]
    assert [b.value for b in buttons if b.selected] == [f"resume:{ids[0]}"]


@pytest.mark.acceptance(spec="channels", scenario="/resume n reopens that conversation")
async def test_resume_n_reopens_that_conversation(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    ids = await _three_conversations(env, resource)

    await env.processor.on_message(inbound("tg", "owner", "/resume 3"))

    assert await env.active_conversation(resource) == ids[0]
    assert adapter.texts()[-1] == "↩️ Resumed \u201cone\u201d with Coffer Assistant."

    await env.processor.on_message(inbound("tg", "owner", "/resume 9"))
    assert adapter.texts()[-1] == "No conversation #9 — send /resume to see the list."
    assert await env.active_conversation(resource) == ids[0]


@pytest.mark.acceptance(
    spec="channels", scenario="/resume never offers another chat's conversation"
)
async def test_resume_never_offers_another_chats_conversation(env: ChannelEnv) -> None:
    resource, adapter = await _card_channel(env)
    await env.pair(resource, "other-chat")
    await env.processor.on_message(inbound("tg", "other-chat", "/new"))
    foreign = await env.active_conversation(resource, "other-chat")
    assert foreign is not None
    web = await env.chat.create_conversation(agent_key="builtin", agent_config=None)
    ids = await _three_conversations(env, resource)

    await env.processor.on_message(inbound("tg", "owner", "/resume"))
    [(_chat, _text, buttons)] = [c for c in _resume_cards(adapter) if c[0] == "owner"]
    assert {b.value for b in buttons} == {f"resume:{i}" for i in ids}

    # A forged tap naming another chat's (or the web's) conversation is refused.
    for stranger in (foreign, web.id):
        await env.processor.on_callback(tap_event("tg", "owner", f"resume:{stranger}"))
        assert "not one of this chat's" in adapter.texts()[-1]
    assert await env.active_conversation(resource) == ids[-1]
    assert await env.active_conversation(resource, "other-chat") == foreign


@pytest.mark.acceptance(
    spec="channels", scenario="/resume pages through every earlier conversation"
)
async def test_resume_pages_through_every_earlier_conversation(env: ChannelEnv) -> None:
    resource, adapter = await _card_channel(env)
    ids = []
    for n in range(1, 10):
        await env.processor.on_message(inbound("tg", "owner", "/new"))
        conversation_id = await env.active_conversation(resource)
        assert conversation_id is not None
        await env.chat.rename_conversation(conversation_id, new_title=f"task {n}")
        ids.append(conversation_id)
    newest_first = list(reversed(ids))

    await env.processor.on_message(inbound("tg", "owner", "/resume"))

    [(_chat, text, buttons)] = _resume_cards(adapter)
    assert text.endswith("Page 1/3")
    assert "1 · task 9" in text and "5 · task 5" not in text
    assert [b.label for b in buttons][:4] == ["✓ 1", "2", "3", "4"]

    await env.processor.on_callback(
        tap_event("tg", "owner", "page:resume:2", platform_message_id="c-1")
    )

    _chat, _mid, text, buttons, _title = adapter.card_updates[-1]
    assert "9 · task 1" in text and "1 · task 9" not in text
    # Numbering stays global: the last page's only button is the 9th conversation.
    assert [b.value for b in buttons if b.value.startswith("resume:")] == [
        f"resume:{newest_first[8]}"
    ]
    assert buttons[0].label == "9"

    await env.processor.on_message(inbound("tg", "owner", "/resume 9"))
    assert await env.active_conversation(resource) == ids[0]
