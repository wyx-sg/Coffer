"""ChannelRuntime reconciliation: enable/disable, delete cleanup, the websocket.

Real ResourceService + real SQLite drive the runtime; the adapter factory and
the websocket controller are the recording fakes from conftest.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import ResourceNotFound

from .conftest import ChannelEnv

_SEATALK_CONFIG = {
    "channel_type": "seatalk",
    "app_id": "app-1",
    "app_secret_ref": "channel/st/app",
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

    await env.resources.set_enabled(resource.uid, False, actor="cli")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is False
    assert first.stopped is True
    assert env.processor.binding("tg") is None

    await env.resources.set_enabled(resource.uid, True, actor="cli")
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
    assert (await env.peers.owner_peer(resource.id)) is not None

    await env.resources.delete(resource.uid, actor="cli")

    # on_delete → runtime.evict: adapter stopped, binding gone, pairing dropped.
    assert adapter.stopped is True
    assert env.runtime.is_running("tg") is False
    assert env.processor.binding("tg") is None
    assert env.pairing.pending("tg") is False
    # The resource row is gone and the peer row went with it (FK cascade).
    with pytest.raises(ResourceNotFound):
        await env.resources.get(resource.uid)
    assert await env.peers.owner_peer(resource.id) is None


async def test_the_websocket_tracks_the_enabled_seatalk_channel(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    resource = await env.resources.register(
        kind="channel", name="st", config=await env.bound(_SEATALK_CONFIG), actor="cli"
    )

    await env.runtime.reconcile_once()
    # Held with the app's own materialized credentials, keyed by the channel's
    # UID — the register handshake is per key, and a label the owner may
    # rename is the wrong thing to hold one on.
    assert env.runtime.is_running("st") is True
    assert env.websockets.started == {resource.uid: ("app-1", "app-secret-value")}
    status = await env.service.status(resource.uid)
    assert status.inbound is not None
    assert status.inbound.websocket_state == "connecting"

    await env.resources.set_enabled(resource.uid, False, actor="cli")
    await env.runtime.reconcile_once()
    assert env.websockets.running(resource.uid) is False
    assert resource.uid in env.websockets.stopped

    await env.resources.set_enabled(resource.uid, True, actor="cli")
    await env.runtime.reconcile_once()
    assert env.websockets.started == {resource.uid: ("app-1", "app-secret-value")}


async def test_a_document_still_carrying_webhook_keys_connects_the_same_way(
    env: ChannelEnv,
) -> None:
    """A channel document from a machine on an older build may still carry the
    webhook-era keys; they are ignored and the channel holds its websocket."""
    env.keyring.set("channel/st/app", "app-secret-value")
    resource = await env.resources.register(
        kind="channel",
        name="st",
        config=await env.bound(
            {
                **_SEATALK_CONFIG,
                "delivery": "webhook",
                "signing_secret_ref": "channel/st/sign",
                "tunnel_token_ref": "channel/st/tunnel",
            }
        ),
        actor="cli",
    )

    await env.runtime.reconcile_once()

    assert env.websockets.started == {resource.uid: ("app-1", "app-secret-value")}


async def test_deleting_a_websocket_channel_stops_its_connection(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    resource = await env.resources.register(
        kind="channel", name="st", config=await env.bound(_SEATALK_CONFIG), actor="cli"
    )
    await env.runtime.reconcile_once()
    assert env.websockets.running(resource.uid) is True

    await env.resources.delete(resource.uid, actor="cli")

    # on_delete → runtime.evict: the held connection goes with the channel.
    assert resource.uid in env.websockets.stopped
    assert env.websockets.running(resource.uid) is False


async def test_dispose_releases_every_held_connection(env: ChannelEnv) -> None:
    env.keyring.set("channel/st/app", "app-secret-value")
    resource = await env.resources.register(
        kind="channel", name="st", config=await env.bound(_SEATALK_CONFIG), actor="cli"
    )
    await env.runtime.reconcile_once()
    assert env.websockets.running(resource.uid) is True

    await env.runtime.dispose()

    assert env.websockets.disposed == 1
    assert env.websockets.active() == set()


async def test_telegram_only_deployment_holds_no_websocket(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert env.websockets.started == {}
    status = await env.service.status(resource.uid)
    assert status.inbound is None
