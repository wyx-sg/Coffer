"""ChannelRuntime reconciliation: enable/disable, delete cleanup, the listener.

Real ResourceService + real SQLite drive the runtime; the adapter factory and
the listener controller are the recording fakes from conftest.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import ResourceNotFound

from .conftest import ChannelEnv

_SEATALK_CONFIG = {
    "channel_type": "seatalk",
    "app_id": "app-1",
    "app_secret_ref": "channel/st/app",
    "signing_secret_ref": "channel/st/sign",
}


@pytest.mark.acceptance(
    spec="009-channels", scenario="disable stops the adapter and enable restarts it"
)
async def test_disable_stops_the_adapter_and_enable_restarts_it(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")

    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert len(env.created_adapters) == 1
    first = env.created_adapters[0]
    assert first.started is True
    assert first.callbacks is not None  # inbound delivery wired to the processor
    assert env.processor.binding("tg") is not None

    await env.resources.set_enabled(resource.ref, False, actor="cli")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is False
    assert first.stopped is True
    assert env.processor.binding("tg") is None

    await env.resources.set_enabled(resource.ref, True, actor="cli")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert len(env.created_adapters) == 2
    second = env.created_adapters[1]
    assert second is not first
    assert second.started is True
    assert second.stopped is False


@pytest.mark.acceptance(
    spec="009-channels", scenario="deleting a channel cleans up its runtime and peer"
)
async def test_delete_stops_the_adapter_and_removes_the_peer_row(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    adapter = env.created_adapters[0]
    await env.pair(resource, chat_id="owner")
    env.pairing.issue("tg")
    assert (await env.peers.get(resource.id)) is not None

    await env.resources.delete(resource.ref, actor="cli")

    # on_delete → runtime.evict: adapter stopped, binding gone, pairing dropped.
    assert adapter.stopped is True
    assert env.runtime.is_running("tg") is False
    assert env.processor.binding("tg") is None
    assert env.pairing.pending("tg") is False
    # The resource row is gone and the peer row went with it (FK cascade).
    with pytest.raises(ResourceNotFound):
        await env.resources.get(resource.ref)
    assert await env.peers.get(resource.id) is None


@pytest.mark.acceptance(
    spec="009-channels", scenario="the listener runs only while a seatalk channel is enabled"
)
async def test_listener_tracks_the_enabled_seatalk_channel(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    env.keyring.set("channel/st/sign", "signing-secret-value")
    resource = await env.resources.register(
        kind="channel", name="st", config=_SEATALK_CONFIG, actor="cli"
    )

    await env.runtime.reconcile_once()
    assert env.listener.running() is True
    # The listener got the channel's materialized signing secret.
    assert env.listener.ensure_running_calls[-1] == {"st": "signing-secret-value"}

    await env.resources.set_enabled(resource.ref, False, actor="cli")
    await env.runtime.reconcile_once()
    assert env.listener.running() is False
    assert env.listener.ensure_stopped_calls >= 1

    await env.resources.set_enabled(resource.ref, True, actor="cli")
    await env.runtime.reconcile_once()
    assert env.listener.running() is True
    assert env.listener.ensure_running_calls[-1] == {"st": "signing-secret-value"}


async def test_telegram_only_deployment_keeps_the_listener_stopped(env: ChannelEnv) -> None:
    await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert env.listener.running() is False
    assert env.listener.ensure_running_calls == []
