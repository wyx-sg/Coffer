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
