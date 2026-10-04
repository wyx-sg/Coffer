"""Sender-identity owner gate + first-class channel-driven audit.

See "Gate inbound traffic on sender identity".
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until

# -- sender-identity gate ------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a group member who is not the paired sender is ignored"
)
async def test_message_from_a_different_sender_is_ignored(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    # Same chat id (e.g. a group), but a different member sends it.
    await env.processor.on_message(inbound("tg", "owner", "do something", sender_id="u-intruder"))

    assert adapter.texts() == []  # no reply
    assert await env.conversations() == []  # no turn started


async def test_matching_sender_passes_the_gate(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id="u-owner"))
    await wait_until(lambda: "Hello world" in adapter.texts())


@pytest.mark.acceptance(
    spec="channels", scenario="a direct message that names no sender is ignored"
)
async def test_message_with_no_sender_id_is_ignored(env: ChannelEnv) -> None:
    # Ownership that cannot be proven is not ownership — the same rule the group
    # gate applies. A transport that cannot name a sender reaches no turn.
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id=""))

    assert adapter.texts() == []
    assert await env.conversations() == []
