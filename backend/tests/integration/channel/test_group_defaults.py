"""A group's threads each keep their own agent, model and directory, and a new
thread starts from the channel's defaults (spec channels "Keep a chat's agent,
model and directory across its conversations"); the direct-chat commands only
answer where they work.

A SeaTalk main-chat @mention roots a new thread at itself, so ``thread_id`` is
the message's own id: a command there is about that new thread like any other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.domain.channel.commands import DM_ONLY_NOTICE

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, wait_until

GROUP = "grp-1"


def _main(text: str, message_id: str = "m-1") -> object:
    return inbound(
        "tg",
        GROUP,
        text,
        chat_kind="group",
        sender_id="owner-1",
        thread_id=message_id,
        platform_message_id=message_id,
    )


def _in_thread(text: str, thread_id: str) -> object:
    return inbound("tg", GROUP, text, chat_kind="group", sender_id="owner-1", thread_id=thread_id)


async def _channel(
    env: ChannelEnv, directories: list[str] = ()
) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(), directories=directories)
    await env.pair(resource, "owner", sender_id="owner-1")
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="a new group thread starts from the channel's defaults"
)
async def test_a_new_group_thread_starts_from_the_channels_defaults(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await _channel(env)

    # /new codex in the main chat opens its own thread on Codex.
    await env.processor.on_message(_main("/new codex", "m-1"))
    first = await env.active_conversation(resource, GROUP, "m-1")
    assert first is not None
    assert (await env.chat.get_conversation(first)).agent_key == "codex"
    assert adapter.texts()[-1].startswith("🆕 New conversation · Codex")

    # The next thread keeps nothing of it: it opens on the channel's default.
    await env.send(_in_thread("hello", "th-2"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    second = await env.active_conversation(resource, GROUP, "th-2")
    assert second is not None
    assert (await env.chat.get_conversation(second)).agent_key == "builtin"


@pytest.mark.acceptance(
    spec="channels", scenario="a direct-chat command in a group is declined with one line"
)
async def test_a_dm_only_command_in_a_group_is_declined_and_changes_nothing(
    env: ChannelEnv, tmp_path: Path
) -> None:
    resource, adapter = await _channel(env, [str(tmp_path)])

    for command in ("/model gpt-5 high", f"/dir {tmp_path}", "/status", "/resume", "/thread x"):
        before = len(adapter.sent)
        await env.processor.on_message(_main(command, "m-1"))
        assert adapter.texts()[before:] == [DM_ONLY_NOTICE]

    assert await env.threads.get(resource.uid, GROUP, "") is None
    assert await env.threads.get(resource.uid, GROUP, "m-1") is None
    # Nothing reached the agent as a message.
    assert await env.active_conversation(resource, GROUP, "m-1") is None
