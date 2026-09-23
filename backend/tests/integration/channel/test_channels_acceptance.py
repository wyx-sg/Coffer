"""Acceptance tests for the `channels` requirements whose scenarios were written
during the OpenSpec rewrite: the audit surface, per-thread queueing, thread-aware
outbound media, health diagnostics, and private group chatter.

Everything runs through the real channel core and chat platform over SQLite;
only the IM transport is the recording fake from ``conftest``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, TextBlock
from coffer.infrastructure.channel.telegram_profile import BotIdentity

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    Resource,
    default_reply_adapter,
    inbound,
    turn_body,
    wait_until,
)


def _mark_running(env: ChannelEnv, resource: Resource, adapter: FakeChannelAdapter) -> None:
    """Make the runtime report ``adapter`` as this channel's live adapter, which
    is what notify and status read — without waiting on the reconciler."""
    env.runtime._running[resource.name] = SimpleNamespace(adapter=adapter)


@pytest.mark.acceptance(
    spec="channels", scenario="notifications and turns leave no channel audit entry"
)
async def test_notifications_and_turns_leave_no_channel_audit_entry(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    _mark_running(env, resource, adapter)
    code, _expires, _link = await env.service.issue_pairing_code(resource.uid, actor="test")
    await env.processor.on_message(inbound("tg", "owner", code, sender_id="4242"))
    assert await env.peers.owner_peer(resource.id) is not None

    before = await env.audit.query(resource=resource, limit=500)
    channel_specific = sorted(e.event_type for e in before if e.event_type.startswith("channel_"))
    assert channel_specific == ["channel_paired", "channel_pairing_issued"]

    await env.service.notify(resource.uid, "build finished", actor="test")
    assert ("owner", "build finished") in adapter.sent
    await env.processor.on_message(inbound("tg", "owner", "hello", sender_id="4242"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    after = await env.audit.query(resource=resource, limit=500)
    assert [(e.event_type, e.id) for e in after] == [(e.event_type, e.id) for e in before]


class _ThreadGate:
    """Scripted agent: a turn whose text starts with ``slow`` blocks on
    ``release``; every other turn answers at once. Records run order."""

    model_id = None

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.runs: list[str] = []

    async def run_turn(
        self, *, history: Sequence[Message], **_: object
    ) -> AsyncIterator[AgentEvent]:
        last = history[-1]
        text = turn_body("".join(b.text for b in last.content if isinstance(b, TextBlock)))

        async def gen() -> AsyncIterator[AgentEvent]:
            self.runs.append(text)
            yield TurnStarted()
            if text.startswith("slow"):
                await self.release.wait()
            yield TextDelta(text=f"echo:{text}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


def _thread_msg(text: str, *, pm: str) -> object:
    return inbound(
        "tg",
        "grp-1",
        text,
        chat_kind="group",
        sender_id="owner-1",
        thread_id="th-A",
        platform_message_id=pm,
    )


@pytest.mark.acceptance(
    spec="channels",
    scenario="a message behind a running thread turn waits in that thread's conversation queue",
)
async def test_a_thread_message_queues_on_its_own_conversation_while_the_dm_runs(
    env: ChannelEnv,
) -> None:
    gate = _ThreadGate()
    env.provider.adapter = gate
    resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(_thread_msg("slow first", pm="p1"))
    await wait_until(lambda: gate.runs == ["slow first"])
    thread_conv = await env.active_conversation(resource, "grp-1", "th-A")
    assert thread_conv is not None

    await env.processor.on_message(_thread_msg("second", pm="p2"))
    await env.processor.on_message(inbound("tg", "owner", "dm now", sender_id="owner-1"))

    # The DM turn runs to completion while the thread turn is still held.
    await wait_until(lambda: "echo:dm now" in adapter.texts())
    dm_conv = await env.active_conversation(resource, "owner", "")
    assert dm_conv is not None and dm_conv != thread_conv
    assert [turn_body(t) for t in env.orchestrator.pending(thread_conv)] == ["second"]
    assert env.orchestrator.pending(dm_conv) == []
    assert "second" not in gate.runs

    gate.release.set()
    await wait_until(lambda: "echo:second" in adapter.texts())
    assert gate.runs == ["slow first", "dm now", "second"]


@pytest.mark.acceptance(
    spec="channels", scenario="a file the agent returns from a thread turn lands in that thread"
)
async def test_a_media_sentinel_from_a_thread_turn_is_sent_into_that_thread(
    env: ChannelEnv, tmp_path: Path
) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"\x89PNG fake")
    env.provider.adapter = default_reply_adapter(f"Here it is.\nMEDIA:{chart}")
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_media=True, supports_groups=True))
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(_thread_msg("draw me a chart", pm="p1"))
    await wait_until(lambda: bool(adapter.media_routed))

    assert adapter.media_routed == [("grp-1", str(chart), None, True, "th-A", "group")]
    # Neither the group main chat nor the owner's DM received the file.
    assert all(thread == "th-A" for _c, _p, _cap, _ph, thread, _k in adapter.media_routed)
    assert all(chat != "owner" for chat, *_ in adapter.media_routed)


class _WithIdentity(FakeChannelAdapter):
    """A transport that reports what the platform told it about the bot — the
    field a platform-side setting surfaces through."""

    def __init__(self, identity: BotIdentity) -> None:
        super().__init__()
        self.identity = identity


@pytest.mark.acceptance(
    spec="channels",
    scenario="a platform setting that defeats the configuration shows on channel health",
)
async def test_a_defeated_configuration_is_diagnosed_on_status(env: ChannelEnv) -> None:
    # Configured to answer un-addressed group messages, while the platform's
    # privacy setting withholds those messages from the bot.
    defeated = await env.register_channel(
        "tg",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg/bot-token",
            "require_mention": False,
        },
    )
    blind = _WithIdentity(BotIdentity(bot_id=1, username="b", reads_all_group_messages=False))
    env.bind(defeated, blind)
    _mark_running(env, defeated, blind)

    honoured = await env.register_channel(
        "tg2",
        ref="channel/tg2/bot-token",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg2/bot-token",
            "require_mention": False,
        },
    )
    sighted = _WithIdentity(BotIdentity(bot_id=2, username="c", reads_all_group_messages=True))
    env.bind(honoured, sighted)
    _mark_running(env, honoured, sighted)

    status = await env.service.status(defeated.uid)
    assert len(status.diagnostics) == 1
    finding = status.diagnostics[0].message
    assert "privacy" in finding.lower()  # names the defeated platform setting
    assert "BotFather" in finding  # and where the fix is made

    assert (await env.service.status(honoured.uid)).diagnostics == ()


@pytest.mark.acceptance(
    spec="channels", scenario="a group command answer is shown only to the asker"
)
async def test_a_group_status_is_private_and_a_group_new_is_visible(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(chat_id="owner", sender_id="4242")

    await env.processor.on_message(
        inbound(
            "tg",
            "-100group",
            "/status",
            chat_kind="group",
            sender_id="4242",
            ephemeral_id="77",
        )
    )
    status_index = len(adapter.sent) - 1
    target = adapter.sent_ephemeral[status_index]
    assert target is not None
    assert target.receiver_id == "4242"
    assert adapter.sent[status_index][0] == "-100group"

    await env.processor.on_message(
        inbound(
            "tg",
            "-100group",
            "/new",
            chat_kind="group",
            sender_id="4242",
            ephemeral_id="78",
            platform_message_id="pm-2",
        )
    )
    assert len(adapter.sent) > status_index + 1
    assert adapter.sent_ephemeral[status_index + 1 :] == [None] * (
        len(adapter.sent) - status_index - 1
    )
    assert adapter.sent[-1][0] == "-100group"
