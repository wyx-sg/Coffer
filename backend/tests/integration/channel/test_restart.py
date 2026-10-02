"""Restarting a channel's adapter, and the secret that makes one restart itself.

Spec channels "Restart a channel's adapter on demand".
"""

from __future__ import annotations

import pytest

from coffer.application.channel.runtime import ChannelRuntime

from .conftest import ChannelEnv, StubWebSocketController, channel_row, uid_of


def _runtime(env: ChannelEnv, stamps: dict[str, str]) -> ChannelRuntime:
    """A runtime over the fixture's parts that can tell a secret was replaced."""
    return ChannelRuntime(
        resources=env.resources,
        adapter_factory=env.adapter_factory,
        processor=env.processor,
        pairing=env.pairing,
        interval_seconds=0.05,
        secret_revision=lambda ref: stamps.get(ref),
    )


@pytest.mark.acceptance(spec="channels", scenario="a restart rebuilds the adapter on demand")
async def test_restart_stops_the_adapter_and_starts_a_fresh_one(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    first = env.created_adapters[0]

    running = await env.service.restart(resource.uid)

    assert running is True
    assert first.stopped is True
    assert len(env.created_adapters) == 2
    assert env.created_adapters[1].started is True
    assert env.runtime.is_running(resource.uid)


@pytest.mark.acceptance(spec="channels", scenario="a restart rebuilds the adapter on demand")
async def test_restart_retries_a_channel_waiting_out_its_failure_ladder(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    env.runtime._failed_at[resource.uid] = 10**12  # failed "just now": retry is held off
    await env.runtime.reconcile_once()
    assert env.created_adapters == []

    assert await env.service.restart(resource.uid) is True
    assert len(env.created_adapters) == 1


async def test_restart_leaves_a_disabled_channel_stopped(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.resources.set_enabled(resource.uid, False, actor="cli")

    assert await env.service.restart(resource.uid) is False
    assert env.created_adapters == []


@pytest.mark.acceptance(spec="channels", scenario="a replaced secret restarts the adapter")
async def test_a_replaced_secret_rebuilds_the_adapter_without_a_restart_call(
    env: ChannelEnv,
) -> None:
    stamps = {"channel/tg/bot-token": "v1"}
    runtime = _runtime(env, stamps)
    await env.register_channel("tg")

    await runtime.reconcile_once()
    await runtime.reconcile_once()
    assert len(env.created_adapters) == 1  # a steady state rebuilds nothing

    stamps["channel/tg/bot-token"] = "v2"  # the token was replaced under the same ref
    await runtime.reconcile_once()

    assert len(env.created_adapters) == 2
    assert env.created_adapters[0].stopped is True
    assert env.created_adapters[1].started is True


@pytest.mark.acceptance(spec="channels", scenario="a replaced secret restarts the adapter")
async def test_a_replaced_app_secret_reconnects_the_websocket() -> None:
    websockets = StubWebSocketController()
    secrets = {"channel/st/secret": "old"}
    stamps = {"channel/st/secret": "v1"}

    async def materialize(refs: dict[str, str], destination: object = None) -> dict[str, str]:
        return {key: secrets[ref] for key, ref in refs.items()}

    runtime = ChannelRuntime(
        resources=None,  # type: ignore[arg-type]
        adapter_factory=None,  # type: ignore[arg-type]
        processor=None,  # type: ignore[arg-type]
        pairing=None,  # type: ignore[arg-type]
        websockets=websockets,
        materialize=materialize,
        secret_revision=lambda ref: stamps.get(ref),
    )
    row = channel_row(
        "st",
        {"channel_type": "seatalk", "app_id": "app-1", "app_secret_ref": "channel/st/secret"},
    )
    await runtime._reconcile_websockets({row.uid: row})
    assert websockets.started[row.uid] == ("app-1", "old")

    secrets["channel/st/secret"] = "new"
    stamps["channel/st/secret"] = "v2"
    await runtime._reconcile_websockets({row.uid: row})

    assert websockets.started[row.uid] == ("app-1", "new")


@pytest.mark.acceptance(spec="channels", scenario="renaming a channel keeps its adapter running")
async def test_renaming_a_channel_does_not_restart_its_adapter(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    adapter = env.created_adapters[0]

    await env.resources.rename(resource.uid, "phone", actor="cli")
    await env.runtime.reconcile_once()

    assert env.created_adapters == [adapter]
    assert adapter.stopped is False
    binding = env.processor.binding(resource.uid)
    assert binding is not None and binding.resource.name == "phone"
    assert uid_of("tg") == resource.uid
