"""A channel switched on but not yet started reports ``starting``, not a fault.

The reconciler converges on its next tick (up to two seconds after the
enable), so a status read in between finds the adapter not running. That gap
must read as "starting" — only a start the runtime actually attempted and that
failed, or a channel that can route nowhere, is "not running". Spec channels
"Report a channel that is starting apart from one that failed to start".
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv


@pytest.mark.acceptance(
    spec="channels", scenario="a channel switched on reports starting until its first start attempt"
)
async def test_an_enabled_channel_reads_starting_until_the_reconciler_starts_it(
    env: ChannelEnv,
) -> None:
    resource = await env.register_channel("tg")
    await env.resources.set_enabled(resource.uid, False, actor="ui")
    await env.runtime.reconcile_once()
    assert (await env.service.status(resource.uid)).starting is False

    await env.resources.set_enabled(resource.uid, True, actor="ui")
    status = await env.service.status(resource.uid)  # before the next tick
    assert status.running is False
    assert status.starting is True

    await env.runtime.reconcile_once()
    status = await env.service.status(resource.uid)
    assert status.running is True
    assert status.starting is False


@pytest.mark.acceptance(
    spec="channels", scenario="a channel switched on reports starting until its first start attempt"
)
async def test_a_failed_start_is_not_starting(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = await env.register_channel("tg")

    async def refuse(_name: str, _config: dict[str, object]) -> object:
        raise RuntimeError("the platform refused the token")

    monkeypatch.setattr(env.runtime, "_factory", refuse)
    await env.runtime.reconcile_once()

    status = await env.service.status(resource.uid)
    assert status.running is False
    assert status.starting is False


async def test_switching_off_and_on_forgets_the_previous_runs_failure(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = await env.register_channel("tg")
    factory = env.runtime._factory

    async def refuse(_name: str, _config: dict[str, object]) -> object:
        raise RuntimeError("the platform refused the token")

    monkeypatch.setattr(env.runtime, "_factory", refuse)
    await env.runtime.reconcile_once()
    assert (await env.service.status(resource.uid)).starting is False

    monkeypatch.setattr(env.runtime, "_factory", factory)
    await env.resources.set_enabled(resource.uid, False, actor="ui")
    await env.runtime.reconcile_once()
    await env.resources.set_enabled(resource.uid, True, actor="ui")

    # The new run has not been attempted yet: the old run's failure is not its.
    assert (await env.service.status(resource.uid)).starting is True
    # ...and it is attempted on the very next tick, not after the failure ladder.
    await env.runtime.reconcile_once()
    assert env.runtime.is_running(resource.uid) is True
