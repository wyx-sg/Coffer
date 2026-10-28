"""Others in a group an owner registered may ask the bot, read-only (spec channels
"Let others in a group ask the bot"): their turn's origin says they are not an
owner, they cannot run commands, and the switch turns it off."""

from __future__ import annotations

import pytest

from coffer.application.channel.prompt_note import ChannelNoteReader

from .conftest import ChannelEnv, inbound, wait_until


async def _owner_registers_group(env: ChannelEnv, *, others_can_ask: bool = True):  # type: ignore[no-untyped-def]
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, others_can_ask=others_can_ask)
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.processor.on_message(
        inbound("tg", "grp", "@bot hi", chat_kind="group", sender_id="owner-1", thread_id="t1")
    )
    await wait_until(lambda: any(r[0] == "grp" for r in adapter.sent_routed))
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="someone else in a registered group is answered read-only"
)
async def test_someone_else_in_a_registered_group_is_answered_read_only(env: ChannelEnv) -> None:
    resource, adapter = await _owner_registers_group(env)
    before = len(adapter.sent_routed)

    await env.processor.on_message(
        inbound(
            "tg",
            "grp",
            "@bot why can't user 42 log in?",
            chat_kind="group",
            sender_id="sam-1",
            sender_display="Sam",
            thread_id="t2",
            platform_message_id="pm-2",
        )
    )
    await wait_until(lambda: len(adapter.sent_routed) > before)

    conv = await env.active_conversation(resource, "grp", "t2")
    assert conv is not None
    prompt = env.raw_prompts(conv)[-1]
    assert "from: Sam (id: sam-1)" in prompt
    assert "asker: not an owner (read-only)" in prompt
    assert not any("owners can use it here" in t for _, t in adapter.sent)


@pytest.mark.acceptance(spec="channels", scenario="an owner's own turn carries no read-only mark")
async def test_an_owners_turn_carries_no_read_only_mark(env: ChannelEnv) -> None:
    resource, _ = await _owner_registers_group(env)

    conv = await env.active_conversation(resource, "grp", "t1")
    assert conv is not None
    assert "not an owner" not in env.raw_prompts(conv)[-1]


@pytest.mark.acceptance(spec="channels", scenario="someone else's command in a group is refused")
async def test_someone_elses_command_is_refused(env: ChannelEnv) -> None:
    _, adapter = await _owner_registers_group(env)
    conversations = len(await env.conversations())

    await env.processor.on_message(
        inbound("tg", "grp", "/new codex", chat_kind="group", sender_id="sam-1", thread_id="t1")
    )

    assert "Commands are for" in adapter.sent[-1][1]
    assert len(await env.conversations()) == conversations


@pytest.mark.acceptance(spec="channels", scenario="others cannot ask once the switch is off")
async def test_others_cannot_ask_with_the_switch_off(env: ChannelEnv) -> None:
    _, adapter = await _owner_registers_group(env, others_can_ask=False)
    conversations = len(await env.conversations())

    await env.processor.on_message(
        inbound("tg", "grp", "@bot hi", chat_kind="group", sender_id="sam-1", thread_id="t2")
    )

    assert "owners can use it here" in adapter.sent[-1][1]
    assert len(await env.conversations()) == conversations


async def test_the_group_note_follows_the_switch(env: ChannelEnv) -> None:
    on = await env.register_channel("tg")
    off = await env.register_channel(
        "tg-off",
        ref="channel/tg-off/bot-token",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg-off/bot-token",
            "others_can_ask": False,
        },
    )
    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )

    assert (await reader.preview(on.uid))["group"].others_can_ask is True
    assert (await reader.preview(on.uid))["direct"].others_can_ask is False
    assert (await reader.preview(off.uid))["group"].others_can_ask is False
