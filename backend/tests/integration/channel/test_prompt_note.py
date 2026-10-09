"""The channel kind reads the facts a channel-driven turn's note is written
from (spec channels "Tell a channel-driven agent it is on a chat channel")."""

from __future__ import annotations

import pytest

from coffer.application.channel.prompt_note import ChannelNoteReader
from coffer.domain.chat.channel_note import ChannelNote

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


@pytest.mark.acceptance(
    spec="channels", scenario="the note lists what renders on the platform the turn is on"
)
async def test_the_note_names_platform_chat_kind_and_what_the_transport_renders(
    env: ChannelEnv,
) -> None:
    resource = await env.register_channel()
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_edit=False, render_notes="This chat renders bold.")
    )
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: bool(adapter.texts()))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )

    assert await reader(resource.uid, conversation_id) == ChannelNote(
        name="tg",
        platform="Telegram",
        chat_kind="direct",
        in_thread=False,
        renders="This chat renders bold.",
    )


async def test_a_deleted_channel_has_no_facts(env: ChannelEnv) -> None:
    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )
    assert await reader("00000000000000000000000000", "c1") is None


_PROMPTS = {
    "channel_type": "telegram",
    "bot_token_ref": "channel/tg/bot-token",
    "direct_system_prompt": "Answer in Chinese.",
    "group_system_prompt": "Name the ticket number first.",
}


def _group(text: str, thread_id: str, *, main: bool = False) -> object:
    return inbound(
        "tg",
        "grp-1",
        text,
        chat_kind="group",
        sender_id="owner",
        thread_id=thread_id,
        platform_message_id=thread_id if main else "pm-1",
        group_main=main,
    )


@pytest.mark.acceptance(spec="channels", scenario="each chat kind reads its own system prompt")
async def test_each_chat_kind_reads_its_own_prompt(env: ChannelEnv) -> None:
    resource = await env.register_channel(config=dict(_PROMPTS))
    adapter = env.bind(resource)
    await env.pair(resource, "owner")
    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    # A group's main chat roots a thread at the message; a reply inside a
    # thread continues that thread's own conversation.
    await env.processor.on_message(_group("hi", "m-1", main=True))  # type: ignore[arg-type]
    await env.processor.on_message(_group("hi", "t-1"))  # type: ignore[arg-type]
    await wait_until(lambda: len(adapter.texts()) >= 3)

    direct = await env.active_conversation(resource)
    main = await env.active_conversation(resource, "grp-1", "m-1")
    thread = await env.active_conversation(resource, "grp-1", "t-1")
    assert direct and main and thread

    assert (await reader(resource.uid, direct)).owner_prompt == "Answer in Chinese."  # type: ignore[union-attr]
    for conversation_id in (main, thread):
        note = await reader(resource.uid, conversation_id)
        assert note is not None
        assert note.chat_kind == "group"
        assert note.owner_prompt == "Name the ticket number first."


@pytest.mark.acceptance(
    spec="channels", scenario="an edited system prompt applies from the next turn"
)
async def test_an_edited_prompt_is_read_on_the_next_turn_without_a_restart(
    env: ChannelEnv,
) -> None:
    resource = await env.register_channel(config=dict(_PROMPTS))
    adapter = env.bind(resource)
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: bool(adapter.texts()))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )

    stored = (await env.resources.get(resource.uid)).config
    await env.resources.update_config(
        resource.uid, {**stored, "direct_system_prompt": "Answer in English."}, actor="test"
    )
    note = await reader(resource.uid, conversation_id)
    assert note is not None and note.owner_prompt == "Answer in English."

    await env.resources.update_config(
        resource.uid, {**stored, "direct_system_prompt": ""}, actor="test"
    )
    cleared = await reader(resource.uid, conversation_id)
    assert cleared is not None and cleared.owner_prompt == ""


@pytest.mark.acceptance(
    spec="channels", scenario="the note names the thread-reading tool where threads can be read"
)
async def test_a_transport_that_reads_threads_says_so_in_the_note(env: ChannelEnv) -> None:
    resource = await env.register_channel("st")
    adapter = env.bind(resource, FakeChannelAdapter(supports_history_fetch=True))
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("st", "owner", "hi"))
    await wait_until(lambda: bool(adapter.texts()))
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    reader = ChannelNoteReader(
        resources=env.resources, threads=env.threads, binding=env.processor.binding
    )

    note = await reader(resource.uid, conversation_id)

    assert note is not None and note.reads_threads is True
