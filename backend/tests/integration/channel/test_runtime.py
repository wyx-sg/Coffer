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
    spec="channels", scenario="disable stops the adapter and enable restarts it"
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
    spec="channels", scenario="deleting a channel cleans up its runtime and peer"
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
    spec="channels", scenario="the listener runs only while a seatalk channel is enabled"
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


_WEBSOCKET_CONFIG = {
    "channel_type": "seatalk",
    "app_id": "app-1",
    "app_secret_ref": "channel/st/app",
    "delivery": "websocket",
}


@pytest.mark.acceptance(
    spec="channels", scenario="a websocket channel runs without the listener or a tunnel"
)
async def test_websocket_only_deployment_keeps_the_listener_stopped(env: ChannelEnv) -> None:
    """FR-071: websocket delivery needs no inbound HTTP surface at all.

    The adapter still runs (it sends the replies), and the connection is held —
    but nothing listens on a port and no tunnel is managed, which is the entire
    reason the transport exists.
    """
    env.keyring.set("channel/st/app", "app-secret-value")
    await env.resources.register(kind="channel", name="st", config=_WEBSOCKET_CONFIG, actor="cli")

    await env.runtime.reconcile_once()

    assert env.runtime.is_running("st") is True
    assert env.listener.running() is False
    assert env.listener.ensure_running_calls == []
    # The connection is held instead, with the app's own materialized credentials.
    assert env.websockets.started == {"st": ("app-1", "app-secret-value")}
    # Nothing on this channel reports webhook ingress.
    status = await env.service.status("st")
    assert status.callback is not None
    assert status.callback.delivery == "websocket"
    assert status.callback.listener_running is False
    assert status.callback.tunnel_managed is False
    assert status.callback.public_callback_url is None
    assert status.callback.websocket_state == "connecting"


async def test_a_webhook_channel_beside_a_websocket_one_still_runs_the_listener(
    env: ChannelEnv,
) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    env.keyring.set("channel/st/sign", "signing-secret-value")
    await env.resources.register(kind="channel", name="hook", config=_SEATALK_CONFIG, actor="cli")
    await env.resources.register(kind="channel", name="ws", config=_WEBSOCKET_CONFIG, actor="cli")

    await env.runtime.reconcile_once()

    # Only the webhook channel's secret reaches the listener; the websocket one
    # has no signing secret to give it.
    assert env.listener.running() is True
    assert env.listener.ensure_running_calls[-1] == {"hook": "signing-secret-value"}
    assert set(env.websockets.started) == {"ws"}


async def test_deleting_a_websocket_channel_stops_its_connection(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    resource = await env.resources.register(
        kind="channel", name="st", config=_WEBSOCKET_CONFIG, actor="cli"
    )
    await env.runtime.reconcile_once()
    assert env.websockets.running("st") is True

    await env.resources.delete(resource.ref, actor="cli")

    # on_delete → runtime.evict: the held connection goes with the channel.
    assert "st" in env.websockets.stopped
    assert env.websockets.running("st") is False


async def test_dispose_releases_every_held_connection(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    await env.resources.register(kind="channel", name="st", config=_WEBSOCKET_CONFIG, actor="cli")
    await env.runtime.reconcile_once()
    assert env.websockets.running("st") is True

    await env.runtime.dispose()

    assert env.websockets.disposed == 1
    assert env.websockets.active() == set()


async def test_telegram_only_deployment_keeps_the_listener_stopped(env: ChannelEnv) -> None:
    await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert env.listener.running() is False
    assert env.listener.ensure_running_calls == []
