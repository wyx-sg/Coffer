"""Closing a parallel thread — by `/close` inside it, or by the idle sweep — and
what a closed thread answers (spec channels "Open parallel conversations beside
a direct chat").

The transport is the recording fake; the processor, the thread store and the
chat platform are real. SeaTalk-shaped (``direct_threads_are_replies=True``):
the platform where a closed thread falling back to the direct chat's own
conversation would be the bug.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel.parallel_threads import CLOSED_NOTICE
from coffer.application.channel.thread_sweep import IDLE_CLOSE_AFTER, ParallelThreadSweep
from coffer.application.chat.turn_state import is_running
from coffer.domain.resource import Resource

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until
from .test_queue_and_stop import GatedAdapter


async def _seatalk_shaped(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel()
    adapter = env.bind(resource, FakeChannelAdapter(direct_threads_are_replies=True))
    await env.pair(resource, "owner")
    return resource, adapter


def _answers_in(adapter: FakeChannelAdapter, thread_id: str) -> list[str]:
    return [text for _chat, text, thread, _kind in adapter.sent_routed if thread == thread_id]


async def _open(env: ChannelEnv, title: str, root: str) -> None:
    await env.processor.on_message(
        inbound("tg", "owner", f"/thread {title}", platform_message_id=root)
    )


def _sweep(env: ChannelEnv, now: datetime) -> ParallelThreadSweep:
    return ParallelThreadSweep(
        threads=env.threads,
        conversations=env.chat,
        turns=env.orchestrator,
        is_running=is_running,
        now=lambda: now,
    )


async def test_closed_rows_stay_and_their_numbers_are_never_reused(env: ChannelEnv) -> None:
    resource, _adapter = await _seatalk_shaped(env)
    await _open(env, "one", "t1")
    await _open(env, "two", "t2")

    assert await env.threads.close_parallel(resource.uid, "owner", "t1") is True
    # Closing twice, or closing what is not a parallel thread, closes nothing.
    assert await env.threads.close_parallel(resource.uid, "owner", "t1") is False
    assert await env.threads.close_parallel(resource.uid, "owner", "") is False

    open_marks = [r.parallel_mark for r in await env.threads.list_parallel(resource.uid, "owner")]
    assert open_marks == ["🧵#2 two"]
    every = await env.threads.list_parallel(resource.uid, "owner", include_closed=True)
    assert [(r.parallel_mark, r.parallel_closed) for r in every] == [
        ("🧵#2 two", False),
        ("🧵#1 one", True),
    ]
    assert [r.thread_id for r in await env.threads.open_parallel_threads()] == ["t2"]
    # Closing #2 as well still leaves #3 as the next number.
    await env.threads.close_parallel(resource.uid, "owner", "t2")
    assert await env.threads.next_parallel_ordinal(resource.uid, "owner") == 3


@pytest.mark.acceptance(spec="channels", scenario="/close closes the parallel thread it is sent in")
async def test_close_inside_a_parallel_thread_closes_it(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")
    await _open(env, "write docs", "t2")
    await env.processor.on_message(inbound("tg", "owner", "is it green?", thread_id="t1"))
    await wait_until(lambda: "Hello world" in _answers_in(adapter, "t1"))
    parallel = await env.active_conversation(resource, "owner", "t1")

    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="t1"))

    assert _answers_in(adapter, "t1")[-1] == (
        "🔒 Closed 🧵#1 deploy check. Send /thread in the chat to open a new one."
    )
    # Its conversation and history stay where the web shows them.
    assert parallel is not None
    assert (await env.chat.get_conversation(parallel)).title == "🧵#1 deploy check"
    assert env.user_texts(parallel) == ["is it green?"]
    # The direct chat's /status counts and lists the open thread only.
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert adapter.texts()[-1].splitlines()[-1] == (
        "Parallel threads (1): 🧵#2 write docs · Coffer Assistant · idle"
    )
    # A closed thread's number is not given out again.
    await _open(env, "third", "t3")
    assert adapter.opened_threads[-1][1] == "🧵#3 third"


async def test_status_lists_nothing_once_every_thread_is_closed(env: ChannelEnv) -> None:
    _resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")
    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="t1"))
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    assert "Parallel threads" not in adapter.texts()[-1]


async def test_close_outside_a_parallel_thread_is_refused(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")

    # The direct chat itself, and a casual reply-in-thread of it.
    await env.processor.on_message(inbound("tg", "owner", "/close"))
    assert adapter.texts()[-1] == "Use /close inside a parallel thread."
    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="m-root"))
    assert _answers_in(adapter, "m-root")[-1] == "Use /close inside a parallel thread."
    assert len(await env.threads.list_parallel(resource.uid, "owner")) == 1


@pytest.mark.acceptance(
    spec="channels", scenario="/close in a thread running a turn asks for /stop first"
)
async def test_close_while_a_turn_runs_asks_for_stop_first(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.processor.on_message(inbound("tg", "owner", "long job", thread_id="t1"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)

    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="t1"))

    assert _answers_in(adapter, "t1")[-1] == (
        "A turn is running here — send /stop first, then /close."
    )
    assert len(await env.threads.list_parallel(resource.uid, "owner")) == 1
    gated.release.set()


@pytest.mark.acceptance(
    spec="channels", scenario="a message in a closed thread is answered there and runs nothing"
)
async def test_a_message_in_a_closed_thread_is_answered_there_and_runs_nothing(
    env: ChannelEnv,
) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await env.processor.on_message(inbound("tg", "owner", "remember 7"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    dm_conversation = await env.active_conversation(resource)
    await _open(env, "deploy check", "t1")
    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="t1"))
    turns_before = len(env.provider.turns)

    await env.processor.on_message(inbound("tg", "owner", "still there?", thread_id="t1"))
    await env.processor._burst.settled()

    assert _answers_in(adapter, "t1")[-1] == CLOSED_NOTICE
    assert len(env.provider.turns) == turns_before
    # Never folded into the direct chat's own conversation.
    assert dm_conversation is not None
    assert env.user_texts(dm_conversation) == ["remember 7"]
    # A command that would open a conversation there gets the same notice;
    # /status still reports, and says the thread is closed.
    await env.processor.on_message(inbound("tg", "owner", "/new", thread_id="t1"))
    assert _answers_in(adapter, "t1")[-1] == CLOSED_NOTICE
    await env.processor.on_message(inbound("tg", "owner", "/status", thread_id="t1"))
    status = _answers_in(adapter, "t1")[-1].splitlines()
    assert status[:2] == ["Status", "🧵#1 deploy check"] and status[3] == "Closed"
    await env.processor.on_message(inbound("tg", "owner", "/close", thread_id="t1"))
    assert _answers_in(adapter, "t1")[-1] == "🧵#1 deploy check is already closed."


@pytest.mark.acceptance(spec="channels", scenario="an idle parallel thread closes on its own")
async def test_the_sweep_closes_a_thread_idle_past_the_window(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "old", "t1")
    await _open(env, "fresh", "t2")
    await env.processor.on_message(inbound("tg", "owner", "hi", thread_id="t1"))
    await wait_until(lambda: "Hello world" in _answers_in(adapter, "t1"))
    sent_before = len(adapter.sent_routed)

    # Just inside the window nothing closes …
    now = datetime.now(tz=UTC)
    assert await _sweep(env, now + IDLE_CLOSE_AFTER - timedelta(minutes=5)).sweep_once() == 0
    # … past it every idle thread does, silently.
    assert await _sweep(env, now + IDLE_CLOSE_AFTER + timedelta(minutes=5)).sweep_once() == 2
    assert await env.threads.list_parallel(resource.uid, "owner") == []
    assert len(adapter.sent_routed) == sent_before
    await env.processor.on_message(inbound("tg", "owner", "back", thread_id="t1"))
    assert _answers_in(adapter, "t1")[-1] == CLOSED_NOTICE


async def test_the_sweep_leaves_a_thread_running_a_turn(env: ChannelEnv) -> None:
    resource, _adapter = await _seatalk_shaped(env)
    await _open(env, "busy", "t1")
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.processor.on_message(inbound("tg", "owner", "long job", thread_id="t1"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)

    later = datetime.now(tz=UTC) + IDLE_CLOSE_AFTER * 2
    assert await _sweep(env, later).sweep_once() == 0
    assert len(await env.threads.list_parallel(resource.uid, "owner")) == 1
    gated.release.set()


async def test_the_sweep_stops_when_its_task_is_cancelled(env: ChannelEnv) -> None:
    sweep = ParallelThreadSweep(
        threads=env.threads,
        conversations=env.chat,
        turns=env.orchestrator,
        is_running=is_running,
        interval_s=0.01,
    )
    task = asyncio.get_running_loop().create_task(sweep.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.acceptance(spec="channels", scenario="/resume inside a closed thread reopens it")
async def test_resume_inside_a_closed_thread_reopens_it(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")
    await env.processor.on_message(inbound("tg", "owner", "first", thread_id="t1"))
    await wait_until(lambda: "Hello world" in _answers_in(adapter, "t1"))
    parallel = await env.active_conversation(resource, "owner", "t1")
    # Closed by the sweep, as most are.
    later = datetime.now(tz=UTC) + IDLE_CLOSE_AFTER * 2
    assert await _sweep(env, later).sweep_once() == 1

    # /resume lists the thread's own conversation, nothing ticked as in effect.
    await env.processor.on_message(inbound("tg", "owner", "/resume", thread_id="t1"))
    listing = _answers_in(adapter, "t1")[-1]
    assert "1 · 🧵#1 deploy check" in listing and "✓" not in listing

    await env.processor.on_message(inbound("tg", "owner", "/resume 1", thread_id="t1"))
    assert _answers_in(adapter, "t1")[-1] == (
        "↩️ Resumed “🧵#1 deploy check” with Coffer Assistant. 🔓 This thread is open again."
    )
    assert [r.thread_id for r in await env.threads.list_parallel(resource.uid, "owner")] == ["t1"]
    # Its idle window starts again from the reopen, so the sweep leaves it.
    assert await _sweep(env, datetime.now(tz=UTC) + timedelta(hours=1)).sweep_once() == 0

    # The next message continues the same conversation, in the thread.
    before = len(_answers_in(adapter, "t1"))
    await env.processor.on_message(inbound("tg", "owner", "second", thread_id="t1"))
    await wait_until(lambda: len(_answers_in(adapter, "t1")) > before)
    assert parallel is not None and env.user_texts(parallel) == ["first", "second"]


async def test_resume_in_an_open_thread_says_nothing_about_reopening(env: ChannelEnv) -> None:
    resource, adapter = await _seatalk_shaped(env)
    await _open(env, "deploy check", "t1")
    await env.processor.on_message(inbound("tg", "owner", "/new", thread_id="t1"))
    await env.processor.on_message(inbound("tg", "owner", "/resume 2", thread_id="t1"))
    assert _answers_in(adapter, "t1")[-1].endswith("with Coffer Assistant.")
    assert await env.threads.reopen_parallel(resource.uid, "owner", "t1") is False
