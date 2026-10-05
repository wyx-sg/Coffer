"""`/status` and `/help` are cards ending in their actions (spec channels
"Report the chat's state as a status card" and "Offer the commands as a help
card")."""

from __future__ import annotations

import pytest

from coffer.domain.channel.commands import help_text

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event

STATUS_IDLE = ["cmd:new", "cmd:model", "cmd:resume", "cmd:dir"]
HELP_PAGES = [
    ["cmd:new", "cmd:stop", "cmd:model", "cmd:dir"],
    ["cmd:status", "cmd:resume", "cmd:thread", "cmd:del"],
    ["cmd:help"],
]


def _commands(buttons) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.value for b in buttons if b.value.startswith("cmd:")]


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
    assert [b.label for b in buttons] == ["New", "Model", "Resume", "Dir"]


@pytest.mark.acceptance(
    spec="channels", scenario="/help is a card with a button for every command, paged"
)
async def test_help_is_a_paged_card_with_a_button_for_every_command(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner")

    await env.processor.on_message(inbound("tg", "owner", "/help"))

    [(_chat, text, buttons)] = adapter.cards
    assert text.startswith(help_text())
    assert text.endswith("Page 1/3")
    assert _commands(buttons) == HELP_PAGES[0]
    assert [b.label for b in buttons][:4] == ["New", "Stop", "Model", "Dir"]

    # Next rewrites the same card with the following commands.
    await env.processor.on_callback(
        tap_event("tg", "owner", "page:help:1", platform_message_id="card-1")
    )
    _c, _m, text, buttons, _t = adapter.card_updates[-1]
    assert text.endswith("Page 2/3")
    assert _commands(buttons) == HELP_PAGES[1]
    await env.processor.on_callback(
        tap_event("tg", "owner", "page:help:2", platform_message_id="card-1")
    )
    assert _commands(adapter.card_updates[-1][3]) == HELP_PAGES[2]
    assert len(adapter.cards) == 1, "a page turn must not post a second card"


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

    # The three-line confirmation, then the help card with every command.
    assert adapter.texts()[0].startswith("✅ Paired — you own tg.")
    [(_chat, text, buttons)] = adapter.cards
    assert text.startswith(help_text())
    assert _commands(buttons) == HELP_PAGES[0]


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

    help_card, new_card = adapter.cards[-2:]
    assert help_card[1] == help_text(group=True)
    assert help_text(group=True).splitlines()[0] == "/new [agent] · /stop · /del · /help"
    assert [b.value for b in help_card[2]] == ["cmd:new", "cmd:stop", "cmd:del", "cmd:help"]
    # The /new card in a group offers Agent alone.
    assert [b.label for b in new_card[2]] == ["Agent"]
    # A direct chat gets all nine.
    assert help_text().count("/") >= 9
