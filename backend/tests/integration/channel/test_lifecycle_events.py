"""The two chat-lifecycle events: the bot removed from a group, and a group
turned external.

Neither drives a turn, and their contracts are opposites: a removal must go
QUIET (stop that chat's live sessions, send nothing into a group the bot is no
longer in), while an external conversion must go LOUD in the group itself — the
owner is the one who needs to know their paired chat can now be read by people
from other organisations, and a daemon log line would never reach them.
"""

from __future__ import annotations

import pytest

from coffer.application.channel.inbound_events import EXTERNAL_GROUP_WARNING

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    default_reply_adapter,
    inbound,
    lifecycle_event,
    wait_until,
)


async def _paired_group(env: ChannelEnv, name: str = "st") -> tuple[FakeChannelAdapter, int]:
    """A channel paired to the owner's DM plus a live group session driven by
    one @mention, so a lifecycle event has something real to tear down."""
    resource = await env.register_channel(name)
    adapter = env.bind(resource, FakeChannelAdapter(supports_groups=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.processor.on_message(
        inbound(
            name,
            "grp-1",
            "@bot hello",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())
    return adapter, resource.id


@pytest.mark.acceptance(
    spec="channels", scenario="being removed from a group stops that group's sessions"
)
async def test_removed_from_group_stops_that_chat_s_sessions_and_stays_silent(
    env: ChannelEnv,
) -> None:
    adapter, _resource_id = await _paired_group(env)
    before = len(adapter.sent)
    assert [key for key in env.processor._sessions if key[1] == "grp-1"]

    await env.processor.on_lifecycle(
        lifecycle_event("st", "grp-1", "removed_from_group", actor_display="Alice")
    )

    # Every session of that chat is gone — its drain task cancelled, its turn
    # interrupted — while the owner's DM session (a different chat) survives.
    assert [key for key in env.processor._sessions if key[1] == "grp-1"] == []
    # Nothing was sent: the bot is out of the group, so a goodbye could only fail.
    assert len(adapter.sent) == before


async def test_removed_from_group_leaves_other_chats_sessions_alone(env: ChannelEnv) -> None:
    adapter, _resource_id = await _paired_group(env)
    await env.processor.on_message(inbound("st", "owner", "hi", sender_id="owner-1"))
    await wait_until(lambda: len([t for t in adapter.texts() if t == "Hello world"]) >= 2)
    assert [key for key in env.processor._sessions if key[1] == "owner"]

    await env.processor.on_lifecycle(lifecycle_event("st", "grp-1", "removed_from_group"))

    assert [key for key in env.processor._sessions if key[1] == "owner"]


@pytest.mark.acceptance(
    spec="channels", scenario="a group turning external is announced in the group"
)
async def test_group_became_external_sends_exactly_one_warning_into_the_group(
    env: ChannelEnv,
) -> None:
    adapter, _resource_id = await _paired_group(env)

    await env.processor.on_lifecycle(
        lifecycle_event("st", "grp-1", "group_became_external", actor_display="Alice")
    )

    warnings = [r for r in adapter.sent_routed if r[1] == EXTERNAL_GROUP_WARNING]
    assert len(warnings) == 1
    chat_id, _text, _thread_id, chat_kind = warnings[0]
    assert (chat_id, chat_kind) == ("grp-1", "group")
    # The channel keeps working — nothing was torn down.
    assert [key for key in env.processor._sessions if key[1] == "grp-1"]


async def test_group_still_answers_after_it_became_external(env: ChannelEnv) -> None:
    adapter, _resource_id = await _paired_group(env)
    await env.processor.on_lifecycle(lifecycle_event("st", "grp-1", "group_became_external"))

    env.provider.adapter = default_reply_adapter("still here")
    await env.processor.on_message(
        inbound(
            "st",
            "grp-1",
            "@bot again",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
            platform_message_id="pm-2",
        )
    )
    await wait_until(lambda: "still here" in adapter.texts())


async def test_unknown_lifecycle_kind_is_a_no_op(env: ChannelEnv) -> None:
    """A kind this version does not model must never raise (it runs on the
    adapter's receive loop) and must change nothing."""
    adapter, _resource_id = await _paired_group(env)
    before = list(adapter.sent)

    await env.processor.on_lifecycle(lifecycle_event("st", "grp-1", "group_renamed"))

    assert adapter.sent == before
    assert [key for key in env.processor._sessions if key[1] == "grp-1"]


async def test_lifecycle_for_an_unpaired_chat_is_ignored(env: ChannelEnv) -> None:
    """The bot merely sat in that group — it was never paired, so there is
    nothing to stop and nobody to warn."""
    adapter, _resource_id = await _paired_group(env)
    before = list(adapter.sent)

    await env.processor.on_lifecycle(lifecycle_event("st", "grp-unknown", "group_became_external"))
    await env.processor.on_lifecycle(lifecycle_event("st", "grp-unknown", "removed_from_group"))

    assert adapter.sent == before


async def test_lifecycle_for_an_unbound_channel_is_ignored(env: ChannelEnv) -> None:
    await _paired_group(env)
    # No raise, no sends — the channel was never bound under this name.
    await env.processor.on_lifecycle(lifecycle_event("nope", "grp-1", "removed_from_group"))
