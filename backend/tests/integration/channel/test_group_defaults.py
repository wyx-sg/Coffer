"""A setting sent in a SeaTalk group's main chat configures the group's
defaults (spec channels "Set a group's defaults from its main chat" and "Keep a
chat's settings across its conversations").

A main-chat @mention roots a new thread at itself, so the message carries
``group_main=True`` and ``thread_id`` = its own id: the answer goes to that
thread, the setting to the group's ``""`` row.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from coffer.application.channel.resume_switch import GROUP_MAIN_RESUME

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, wait_until
from .test_queue_and_stop import GatedAdapter

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
        group_main=True,
    )


def _in_thread(text: str, thread_id: str) -> object:
    return inbound("tg", GROUP, text, chat_kind="group", sender_id="owner-1", thread_id=thread_id)


async def _channel(
    env: ChannelEnv, directories: list[str] = ()
) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_groups=True), directories=directories)
    await env.pair(resource, "owner", sender_id="owner-1")
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels",
    scenario="a setting sent in a SeaTalk group's main chat becomes the default for new threads",
)
async def test_a_main_chat_setting_becomes_the_default_for_new_threads(
    env: ChannelEnv, tmp_path: Path
) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await _channel(env, [str(tmp_path)])

    await env.processor.on_message(_main("/new codex", "m-1"))
    await env.processor.on_message(_main("/model gpt-5 high", "m-2"))
    await env.processor.on_message(_main(f"/dir {tmp_path}", "m-3"))

    row = await env.threads.get(resource.id, GROUP, "")
    assert row is not None
    assert (row.preferred_agent, row.preferred_model, row.preferred_effort, row.preferred_cwd) == (
        "codex",
        "gpt-5",
        "high",
        str(tmp_path),
    )
    # Nothing was opened: neither for the group row nor for the rooted threads.
    for thread in ("", "m-1", "m-2", "m-3"):
        assert await env.active_conversation(resource, GROUP, thread) is None
    answers = [(text, thread) for _chat, text, thread, _kind in adapter.sent_routed]
    assert answers == [
        ("🔀 Agent set to Codex — default for new threads in this group.", "m-1"),
        ("🧠 Model set to gpt-5, effort high — default for new threads in this group.", "m-2"),
        (f"📁 Directory set to {tmp_path} — default for new threads in this group.", "m-3"),
    ]

    # Bare /new there says what the defaults are.
    await env.processor.on_message(_main("/new", "m-4"))
    assert adapter.texts()[-1].startswith(
        f"Defaults for new threads in this group: Codex · gpt-5 · High · {tmp_path}"
    )
    # /resume there points into a thread.
    await env.processor.on_message(_main("/resume", "m-5"))
    assert adapter.texts()[-1] == GROUP_MAIN_RESUME


@pytest.mark.acceptance(spec="channels", scenario="a group thread inherits the group's defaults")
async def test_a_group_thread_inherits_the_groups_defaults(env: ChannelEnv) -> None:
    codex = env.add_agent("codex", reply="codex-here")
    resource, adapter = await _channel(env)
    await env.processor.on_message(_main("/new codex"))
    await env.processor.on_message(_main("/model gpt-5 high", "m-2"))

    # A plain message in the main chat is an ordinary turn in the new thread,
    # and that thread opens on the group's defaults.
    await env.send(_main("hello", "m-9"))
    await wait_until(lambda: "codex-here" in adapter.texts())

    conversation_id = await env.active_conversation(resource, GROUP, "m-9")
    assert conversation_id is not None
    assert (await env.chat.get_conversation(conversation_id)).agent_key == "codex"
    assert codex.last_agent_config == {"model": "gpt-5", "effort": "high"}
    # A thread's own setting wins over the group's.
    await env.processor.on_message(_in_thread("/model low", "th-2"))
    row = await env.threads.get(resource.id, GROUP, "th-2")
    assert row is not None and row.preferred_effort == "low"
    group = await env.threads.get(resource.id, GROUP, "")
    assert group is not None and group.preferred_effort == "high"


@pytest.mark.acceptance(
    spec="channels", scenario="/stop in a SeaTalk group's main chat stops every turn in the group"
)
async def test_stop_in_the_main_chat_stops_every_turn_in_the_group(env: ChannelEnv) -> None:
    resource, adapter = await _channel(env)
    await env.processor.on_message(_main("/stop", "m-0"))
    assert adapter.texts()[-1] == "Nothing is running in this group."

    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.send(_in_thread("deploy the api", "th-1"))
    await env.send(_in_thread("write the docs", "th-2"))
    await wait_until(
        lambda: len(env.processor._running_in_chat("tg", GROUP)) == 2,
        message="both thread turns should be running",
    )
    titles = [
        (await env.chat.get_conversation(await env.active_conversation(resource, GROUP, t))).title
        for t in ("th-1", "th-2")
    ]

    await env.processor.on_message(_main("/status", "m-1"))
    status = adapter.texts()[-1]
    assert "Running in this group (2):" in status

    await env.processor.on_message(_main("/stop", "m-2"))

    reply = adapter.texts()[-1].splitlines()
    assert reply[0] == "⏹ Stopping 2 turns:"
    assert sorted(reply[1:]) == sorted(f"• {t}" for t in titles)
    await wait_until(
        lambda: env.processor._running_in_chat("tg", GROUP) == [],
        message="every turn in the group should have stopped",
    )
    gated.release.set()
    await asyncio.sleep(0)
