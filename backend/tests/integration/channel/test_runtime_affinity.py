"""Runtime affinity: a channel runs only on its bound machine (spec 010).

The conftest runtime has no machine-id provider (tests predate affinity and
keep the unfiltered behavior); these tests build a runtime WITH a provider —
the production wiring — and drive `reconcile_once` against channels bound to
this machine, another machine, and nowhere.
"""

from __future__ import annotations

import pytest

from coffer.application.channel.runtime import ChannelRuntime

from .conftest import ChannelEnv, FakeChannelAdapter

LOCAL = "01LOCALMACHINE00000000000A"
OTHER = "01OTHERMACHINE00000000000B"


def _affinity_runtime(env: ChannelEnv) -> tuple[ChannelRuntime, list[FakeChannelAdapter]]:
    created: list[FakeChannelAdapter] = []

    async def factory(name: str, config: dict[str, object]) -> FakeChannelAdapter:
        adapter = FakeChannelAdapter()
        created.append(adapter)
        return adapter

    async def machine_id() -> str:
        return LOCAL

    runtime = ChannelRuntime(
        resources=env.resources,
        adapter_factory=factory,
        processor=env.processor,
        pairing=env.pairing,
        machine_id=machine_id,
    )
    return runtime, created


@pytest.mark.acceptance(spec="009-channels", scenario="a channel runs on exactly one machine")
async def test_only_the_bound_machine_starts_the_adapter(env: ChannelEnv) -> None:
    await env.register_channel(
        "mine",
        ref="channel/mine/bot-token",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/mine/bot-token",
            "runs_on": LOCAL,
        },
    )
    await env.register_channel(
        "elsewhere",
        ref="channel/elsewhere/bot-token",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/elsewhere/bot-token",
            "runs_on": OTHER,
        },
    )
    await env.register_channel("unbound", ref="channel/unbound/bot-token")

    runtime, created = _affinity_runtime(env)
    await runtime.reconcile_once()
    assert runtime.is_running("mine") is True
    assert runtime.is_running("elsewhere") is False
    assert runtime.is_running("unbound") is False
    assert len(created) == 1


async def test_rebind_moves_the_adapter(env: ChannelEnv) -> None:
    resource = await env.register_channel(
        "movable",
        ref="channel/movable/bot-token",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/movable/bot-token",
            "runs_on": LOCAL,
        },
    )
    runtime, _created = _affinity_runtime(env)
    await runtime.reconcile_once()
    assert runtime.is_running("movable") is True

    # Rebind to the other machine (as a sync import would): this runtime stops.
    await env.resources.update_config(
        resource.ref,
        {**resource.config, "runs_on": OTHER},
        "test",
        allow_lifecycle_kind=True,
    )
    await runtime.reconcile_once()
    assert runtime.is_running("movable") is False


async def test_runtime_without_provider_keeps_legacy_behavior(env: ChannelEnv) -> None:
    """No machine-id provider (single-machine/test wiring): no filtering."""
    await env.register_channel("legacy", ref="channel/legacy/bot-token")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("legacy") is True
