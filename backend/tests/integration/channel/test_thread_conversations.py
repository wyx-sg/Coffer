"""FR-032: each group thread is its own conversation (its own history and its
own turn lock), and FR-040's foundation — one bot runs a different agent in
each thread.

Conversation identity is keyed ``(resource_id, chat_id, thread_id)``: two
threads of one group (same ``chat_id``, the group id) resolve to two different
conversations, so concurrent turns in different threads never collide on a
single conversation ("a turn is already running").
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, TextBlock

from .conftest import ChannelEnv, inbound, wait_until


class GatedAdapter:
    """Scripted agent whose turns block on ``release`` so two threads' turns are
    provably in flight at once; records run order."""

    model_id = None

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.runs: list[str] = []

    async def run_turn(
        self, *, history: Sequence[Message], **_: object
    ) -> AsyncIterator[AgentEvent]:
        last = history[-1]
        text = "".join(b.text for b in last.content if isinstance(b, TextBlock))

        async def gen() -> AsyncIterator[AgentEvent]:
            self.runs.append(text)
            yield TurnStarted()
            await self.release.wait()
            yield TextDelta(text=f"echo:{text}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


def _group_msg(thread_id: str, text: str = "hi") -> object:
    """An owner @mention landing in a group thread."""
    return inbound(
        "tg",
        "grp-1",
        text,
        chat_kind="group",
        addressed=True,
        sender_id="owner-1",
        thread_id=thread_id,
    )


@pytest.mark.acceptance(
    spec="009-channels", scenario="each group thread is an independent conversation"
)
async def test_group_threads_are_independent_conversations(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    # Pair the DM so the group @mention has a known owner sender id to gate on.
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(_group_msg("th-A"))
    await env.processor.on_message(_group_msg("th-B"))
    # Both turns enter concurrently. If the two threads shared one conversation,
    # the second start_turn would raise TurnInProgress and the bot would post the
    # "a turn is already running" notice instead of running the turn.
    await wait_until(lambda: len(gated.runs) >= 2)

    conv_a = await env.active_conversation(resource, "grp-1", "th-A")
    conv_b = await env.active_conversation(resource, "grp-1", "th-B")
    assert conv_a is not None and conv_b is not None
    assert conv_a != conv_b  # each thread is its own conversation
    # Both turns hold their own orchestrator slot at the same time.
    assert conv_a in active_turns()
    assert conv_b in active_turns()
    assert not any("already running" in t for t in adapter.texts())

    gated.release.set()
    await wait_until(lambda: "echo:hi" in adapter.texts())


@pytest.mark.acceptance(
    spec="009-channels", scenario="one bot runs different agents in different threads"
)
async def test_one_bot_runs_different_agents_in_different_threads(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    # Thread A switches to codex; thread B keeps the channel default (builtin).
    await env.processor.on_message(_group_msg("th-A", "/agent codex"))
    await wait_until(lambda: any("codex" in t.lower() for t in adapter.texts()))
    await env.processor.on_message(_group_msg("th-B", "hello"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    conv_a = await env.chat.get_conversation(
        await env.active_conversation(resource, "grp-1", "th-A")
    )
    conv_b = await env.chat.get_conversation(
        await env.active_conversation(resource, "grp-1", "th-B")
    )
    # One bot, one group — but each thread drives its own agent.
    assert conv_a.agent_key == "codex"
    assert conv_b.agent_key == "builtin"
