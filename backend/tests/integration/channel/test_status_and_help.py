"""`/status` and `/help` are cards ending in their actions (spec channels
"Report the chat's state as a status card" and "Offer the commands as a help
card")."""

from __future__ import annotations

import pytest

from coffer.domain.channel.commands import help_text

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound

STATUS_IDLE = ["cmd:new", "cmd:model", "cmd:resume", "cmd:dir"]
HELP = ["cmd:new", "cmd:stop", "cmd:model", "cmd:status", "cmd:resume"]


async def _card_channel(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "owner")
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="/status shows names, not ids, with action buttons"
)
async def test_status_shows_names_not_ids_with_action_buttons(env: ChannelEnv, tmp_path) -> None:
    env.add_agent("claude_code")
    env.model_suggestions.add(
        "claude_code", ["claude-opus-4-8"], labels={"claude-opus-4-8": "Opus 4.8"}
    )
    resource, adapter = await _card_channel(env)
    await env.processor.on_message(inbound("tg", "owner", "/new claude-code"))
    await env.processor.on_message(inbound("tg", "owner", "/model claude-opus-4-8 high"))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await env.chat.rename_conversation(conversation_id, new_title="deploy check")

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    (_chat, text, buttons) = adapter.cards[-1]
    assert adapter.card_titles[-1] == "Status"
    assert text.splitlines() == [
        "deploy check",
        "Claude_Code · Opus 4.8 · High · Default directory",
        "Idle",
    ]
    assert conversation_id not in text
    assert "claude_code" not in text
    # Nothing runs, so there is no Stop.
    assert [b.value for b in buttons] == STATUS_IDLE
    assert [b.label for b in buttons] == ["New", "Model", "Resume", "Dir"]


@pytest.mark.acceptance(spec="channels", scenario="/help is a card with the five actions")
async def test_help_is_a_card_with_the_five_actions(env: ChannelEnv) -> None:
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/help"))

    [(_chat, text, buttons)] = adapter.cards
    assert text == help_text()
    assert [b.value for b in buttons] == HELP
    assert [b.label for b in buttons] == ["New", "Stop", "Model", "Status", "Resume"]


async def test_help_without_buttons_is_the_roster_as_text(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/start"))

    assert adapter.texts() == [help_text()]


@pytest.mark.acceptance(spec="channels", scenario="the help card follows pairing")
async def test_the_help_card_follows_pairing(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    code, _expires = env.pairing.issue(resource.uid)

    await env.processor.on_message(inbound("tg", "chat-1", code))

    # The confirmation, then the help card — once.
    assert adapter.texts()[0] == "✅ Paired. This chat now controls Coffer channel 'tg'."
    assert len(adapter.sent) == 2
    [(chat, text, buttons)] = adapter.cards
    assert chat == "chat-1"
    assert text == help_text()
    assert [b.value for b in buttons] == HELP
