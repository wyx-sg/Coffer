"""Parallel conversations beside a direct chat, and which conversation a
direct-chat thread belongs to (spec channels "Open parallel conversations beside
a direct chat",
"Key conversation identity by channel, chat and thread").

The transport is the recording fake; everything above it — the processor, the
thread store, the chat platform — is real. A SeaTalk-shaped fake
(``direct_threads_are_replies=True``) is where a casual reply-in-thread folds
into the direct chat; a Telegram-shaped one keeps every direct-chat thread its
own.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.channel.parallel_threads import (
    GROUP_ANSWER,
    THREAD_BODY,
)
from coffer.domain.channel.errors import ParallelThreadUnavailable
from coffer.domain.chat.message import TextBlock
from coffer.domain.resource import Resource

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    inbound,
    tap_event,
    turn_body,
    wait_until,
)
from .test_queue_and_stop import GatedAdapter


async def _seatalk_shaped(env: ChannelEnv, **caps: bool) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel()
    adapter = env.bind(resource, FakeChannelAdapter(direct_threads_are_replies=True, **caps))
    await env.pair(resource, "owner")
    return resource, adapter


async def _user_texts(env: ChannelEnv, conversation_id: str) -> list[str]:
    messages = await env.chat.list_messages(conversation_id)
    return [
        turn_body("".join(b.text for b in m.content if isinstance(b, TextBlock)))
        for m in messages
        if m.role == "user"
    ]


def _answers_in(adapter: FakeChannelAdapter, thread_id: str) -> list[str]:
    return [text for _chat, text, thread, _kind in adapter.sent_routed if thread == thread_id]


@pytest.mark.acceptance(spec="channels", scenario="/thread opens a marked parallel conversation")
async def test_thread_opens_a_marked_parallel_conversation(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "first task"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    dm_conversation = await env.active_conversation(resource)
    assert dm_conversation is not None

    await env.processor.on_message(inbound("tg", "owner", "/thread deploy check"))

    assert adapter.opened_threads == [("owner", "🧵#1 deploy check", THREAD_BODY, "t1")]
    parallel = await env.active_conversation(resource, "owner", "t1")
    assert parallel is not None and parallel != dm_conversation
    assert (await env.chat.get_conversation(parallel)).title == "🧵#1 deploy check"

    # A message in the thread runs in the parallel conversation, answered there.
    before = len(_answers_in(adapter, "t1"))
    await env.processor.on_message(
        inbound("tg", "owner", "is it green?", thread_id="t1", platform_message_id="pm-2")
    )
    await wait_until(lambda: len(_answers_in(adapter, "t1")) > before)
    assert await _user_texts(env, parallel) == ["is it green?"]
    # The first message's words never replace the mark as its title.
    assert (await env.chat.get_conversation(parallel)).title == "🧵#1 deploy check"
    # The direct chat's own conversation is untouched.
    assert await env.active_conversation(resource) == dm_conversation
    assert await _user_texts(env, dm_conversation) == ["first task"]


async def test_thread_without_a_title_is_a_numbered_task(env: ChannelEnv) -> None:
    _resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "/thread"))
    await env.processor.on_message(inbound("tg", "owner", "/thread   second   one "))
    assert [mark for _c, mark, _b, _t in adapter.opened_threads] == [
        "🧵#1 Task",
        "🧵#2 second one",
    ]
    long_title = "x" * 200
    await env.processor.on_message(inbound("tg", "owner", f"/thread {long_title}"))
    mark = adapter.opened_threads[-1][1]
    assert mark.startswith("🧵#3 xxx") and mark.endswith("…")
    assert len(mark) <= len("🧵#3 ") + 60


async def test_a_number_is_never_reused_after_new_in_a_parallel_thread(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "/thread one"))
    first = await env.active_conversation(resource, "owner", "t1")

    # /new inside the thread replaces its conversation; the new one keeps the mark.
    await env.processor.on_message(inbound("tg", "owner", "/new", thread_id="t1"))
    fresh = await env.active_conversation(resource, "owner", "t1")
    assert fresh is not None and fresh != first
    assert (await env.chat.get_conversation(fresh)).title == "🧵#1 one"

    await env.processor.on_message(inbound("tg", "owner", "/thread two"))
    assert adapter.opened_threads[-1][1] == "🧵#2 two"


async def test_status_inside_a_parallel_thread_names_its_mark(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "/thread deploy check"))
    await env.processor.on_message(inbound("tg", "owner", "/status", thread_id="t1"))
    status = _answers_in(adapter, "t1")[-1]
    assert status.splitlines()[:2] == ["Status", "🧵#1 deploy check"]
    parallel = await env.active_conversation(resource, "owner", "t1")
    assert parallel is not None and parallel not in status  # names, never ids

    # The direct chat's own /status carries no mark.
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert adapter.texts()[-1].startswith("Status\nNo conversation yet\n")


async def test_thread_in_a_group_opens_nothing(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel(sender_id="owner-1")
    await env.processor.on_message(
        inbound("tg", "grp-1", "/thread x", chat_kind="group", sender_id="owner-1", thread_id="g-t")
    )
    assert adapter.opened_threads == []
    assert adapter.texts()[-1] == GROUP_ANSWER
    assert await env.threads.list_parallel(resource.uid, "grp-1") == []


async def test_thread_that_cannot_be_opened_says_why_and_records_nothing(
    env: ChannelEnv,
) -> None:
    resource, adapter = await _seatalk_shaped(env)
    adapter.open_thread_fails_with = ParallelThreadUnavailable("turn topics on")
    await env.processor.on_message(inbound("tg", "owner", "/thread"))
    assert adapter.texts()[-1] == "turn topics on"
    assert await env.threads.list_parallel(resource.uid, "owner") == []

    adapter.open_thread_fails_with = RuntimeError("socket closed")
    await env.processor.on_message(inbound("tg", "owner", "/thread"))
    assert adapter.texts()[-1] == "⚠️ Could not open a thread — try /thread again."
    assert await env.threads.list_parallel(resource.uid, "owner") == []


@pytest.mark.acceptance(
    spec="channels", scenario="/status in a direct chat lists its parallel threads"
)
async def test_status_in_a_direct_chat_lists_its_parallel_threads(env: ChannelEnv) -> None:
    env.add_agent("codex")
    _resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert "parallel" not in adapter.texts()[-1]

    await env.processor.on_message(inbound("tg", "owner", "/thread deploy check"))
    await env.processor.on_message(inbound("tg", "owner", "/thread write docs"))
    # The second thread runs another agent; the first one runs a turn.
    await env.processor.on_message(inbound("tg", "owner", "/new codex", thread_id="t2"))
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.processor.on_message(inbound("tg", "owner", "long job", thread_id="t1"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)

    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert adapter.texts()[-1].splitlines()[-1] == (
        "Parallel threads: 🧵#2 write docs (idle) · 🧵#1 deploy check (running)"
    )

    # A message behind the running turn shows as queued once the turn is gone.
    await env.processor.on_message(inbound("tg", "owner", "next", thread_id="t1"))
    await env.processor.on_message(inbound("tg", "owner", "/stop", thread_id="t1"))
    await wait_until(
        lambda: env.processor._running_in("tg", "owner", "t1") is None,
        message="the stopped turn never cleared its session",
    )
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert adapter.texts()[-1].splitlines()[-1] == (
        "Parallel threads: 🧵#2 write docs (idle) · 🧵#1 deploy check (1 waiting)"
    )
    gated.release.set()


@pytest.mark.acceptance(
    spec="channels",
    scenario="a casual direct-chat reply-in-thread keeps the direct chat's conversation",
)
async def test_a_casual_reply_in_thread_keeps_the_direct_chats_conversation(
    env: ChannelEnv,
) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "remember the number 7"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    dm_conversation = await env.active_conversation(resource)
    assert dm_conversation is not None

    # A reply-in-thread under the bot's answer, a thread /thread did not open.
    await env.processor.on_message(
        inbound("tg", "owner", "which number?", thread_id="m-root", platform_message_id="pm-2")
    )
    await wait_until(lambda: "Hello world" in _answers_in(adapter, "m-root"))

    # The turn ran in the direct chat's conversation, with its context …
    assert await _user_texts(env, dm_conversation) == ["remember the number 7", "which number?"]
    assert await env.active_conversation(resource, "owner", "m-root") is None
    # … and was answered inside that thread.
    assert _answers_in(adapter, "m-root") == ["Hello world"]


async def test_commands_and_taps_in_a_casual_thread_act_on_the_direct_chat(
    env: ChannelEnv,
) -> None:
    env.add_agent("codex")
    resource, adapter = await _seatalk_shaped(env, supports_buttons=True)
    await env.processor.on_message(inbound("tg", "owner", "/new codex", thread_id="m-root"))
    assert await env.thread_preferred_agent(resource) == "codex"
    assert await env.thread_preferred_agent(resource, "owner", "m-root") is None
    assert _answers_in(adapter, "m-root")[-1].startswith("**🆕 New conversation · Codex")
    first = await env.active_conversation(resource)

    await env.processor.on_callback(tap_event("tg", "owner", "cmd:new", thread_id="m-other"))
    assert await env.active_conversation(resource) not in (None, first)
    assert await env.active_conversation(resource, "owner", "m-other") is None
    assert _answers_in(adapter, "m-other")[-1].startswith("**🆕 New conversation · Codex")


async def test_stop_from_a_casual_thread_stops_the_direct_chats_turn(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    _resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)

    await env.processor.on_message(inbound("tg", "owner", "/stop", thread_id="m-root"))
    assert _answers_in(adapter, "m-root") == ["⏹ Stopping…"]
    gated.release.set()


async def test_every_direct_thread_is_its_own_where_threads_are_deliberate(
    env: ChannelEnv,
) -> None:
    # Telegram-shaped: a private-chat topic only exists because someone made it.
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    await env.processor.on_message(inbound("tg", "owner", "in a topic", thread_id="42"))
    await wait_until(lambda: "Hello world" in _answers_in(adapter, "42"))
    topic = await env.active_conversation(resource, "owner", "42")
    assert topic is not None and topic != await env.active_conversation(resource)
