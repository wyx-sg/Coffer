"""`/status` is a card ending in its actions and `/help` a list to read (spec
channels "Report the chat's state as a status card" and "List the commands with
/help")."""

from __future__ import annotations

import pytest

from coffer.domain.channel.commands import help_text

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound

STATUS_IDLE = ["cmd:model", "cmd:dir"]


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
    await env.processor.on_message(inbound("tg", "owner", "/model claude-opus-4-8"))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await env.chat.rename_conversation(conversation_id, new_title="deploy check")

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    (_chat, text, buttons) = adapter.cards[-1]
    assert adapter.card_titles[-1] == "Status"
    assert text.splitlines() == [
        "deploy check",
        "Claude_Code · Opus 4.8 · Default directory",
        "Idle",
    ]
    assert conversation_id not in text
    assert "claude_code" not in text
    # Nothing runs, so there is no Stop.
    assert [b.value for b in buttons] == STATUS_IDLE
    assert [b.label for b in buttons] == ["Model", "Dir"]


@pytest.mark.acceptance(
    spec="channels", scenario="/help lists one command per line, with no buttons"
)
async def test_help_lists_one_command_per_line_with_no_buttons(env: ChannelEnv) -> None:
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/help"))

    assert adapter.cards == []
    [text] = adapter.texts()
    assert text == help_text()
    lines = text.splitlines()
    assert lines[0] == "**Commands**"
    assert lines[1] == "/new [agent] \u2014 Start a fresh conversation, optionally on another agent"
    assert sum(line.startswith("/") for line in lines) == 9


async def test_help_without_buttons_is_the_roster_as_text(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/start"))

    assert adapter.texts() == [help_text()]


@pytest.mark.acceptance(spec="channels", scenario="the command list follows pairing")
async def test_the_command_list_follows_pairing(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    code, _expires = env.pairing.issue(resource.uid)

    await env.processor.on_message(inbound("tg", "chat-1", code))

    # The three-line confirmation, then the list of every command.
    confirmation, listing = adapter.texts()
    assert confirmation.startswith("✅ Paired — you own tg.")
    assert listing == help_text()
    assert adapter.cards == []


@pytest.mark.acceptance(spec="channels", scenario="a group's help lists only the group commands")
async def test_a_groups_help_lists_only_the_group_commands(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "grp-1", sender_id="owner-1")

    await env.processor.on_message(
        inbound("tg", "grp-1", "/help", chat_kind="group", sender_id="owner-1")
    )
    await env.processor.on_message(
        inbound("tg", "grp-1", "/new", chat_kind="group", sender_id="owner-1")
    )

    assert help_text(group=True) in adapter.texts()
    listed = [line.split()[0] for line in help_text(group=True).splitlines() if line[:1] == "/"]
    assert listed == ["/new", "/stop", "/del", "/help"]
    # The /new card in a group offers Agent alone, and is the only card.
    [new_card] = adapter.cards
    assert [b.label for b in new_card[2]] == ["Agent"]
    # A direct chat gets all nine.
    assert sum(line[:1] == "/" for line in help_text().splitlines()) == 9
