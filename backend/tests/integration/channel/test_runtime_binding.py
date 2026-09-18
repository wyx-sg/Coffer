"""The machine binding decides which daemon runs a channel (spec channels FR-026).

A channel travels between the user's machines now, so the resource table is no
longer a private list — two daemons read the same rows. What keeps them from
both answering one bot is ``runs_on``, and these tests drive the case that
matters by standing up two runtimes over ONE table, exactly as two machines
would after a converge round.

Every test here uses ``env.runtime_for(...)`` rather than the fixture's own
runtime, which is deliberately ungated so that the several hundred tests that
are not about machines keep starting channels the way they always did.
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv

_THIS_MACHINE = "aaaaaaaaaaaaaaaa"
_OTHER_MACHINE = "bbbbbbbbbbbbbbbb"

_TELEGRAM = {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"}


def _config(**overrides: object) -> dict[str, object]:
    return {**_TELEGRAM, **overrides}


@pytest.mark.acceptance(
    spec="channels", scenario="only the machine a channel names starts its adapter"
)
async def test_only_the_bound_machine_starts_the_adapter(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg", config=_config(runs_on=_OTHER_MACHINE))

    here = env.runtime_for(_THIS_MACHINE)
    there = env.runtime_for(_OTHER_MACHINE)

    await here.reconcile_once()
    assert here.is_running("tg") is False
    assert env.created_adapters == []

    # The very same row, read by the machine it names.
    await there.reconcile_once()
    assert there.is_running("tg") is True
    assert len(env.created_adapters) == 1

    # And the surface separates "not running" from "not mine to run", which is
    # the whole reason both fields are on the wire.
    status = await env.service_for(here).status(resource.uid)
    assert status.running is False
    assert status.runs_on == _OTHER_MACHINE
    assert status.runs_here is False
    assert [d.code for d in status.diagnostics] == []

    await there.dispose()


@pytest.mark.acceptance(
    spec="channels", scenario="a channel bound to an unknown machine starts nowhere"
)
async def test_a_binding_no_machine_claims_starts_nowhere(env: ChannelEnv) -> None:
    """Fail closed. "Nobody claims it" must never be read as "so I will".

    Every machine that cannot resolve the id reasons identically, so treating an
    unrecognised binding as permission would have them all start — the
    rival-consumer failure arriving through the back door.
    """
    await env.register_channel("tg", config=_config(runs_on="cccccccccccccccc"))

    for machine in (_THIS_MACHINE, _OTHER_MACHINE):
        runtime = env.runtime_for(machine)
        await runtime.reconcile_once()
        assert runtime.is_running("tg") is False
    assert env.created_adapters == []


@pytest.mark.acceptance(spec="channels", scenario="an unbound channel runs nowhere and says so")
async def test_an_unbound_channel_runs_nowhere_and_is_reported(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")  # no runs_on at all

    for machine in (_THIS_MACHINE, _OTHER_MACHINE):
        runtime = env.runtime_for(machine)
        await runtime.reconcile_once()
        assert runtime.is_running("tg") is False
    assert env.created_adapters == []

    status = await env.service_for(env.runtime_for(_THIS_MACHINE)).status(resource.uid)
    assert status.runs_on is None
    assert status.runs_here is False
    assert "channel_not_bound" in [d.code for d in status.diagnostics]


@pytest.mark.acceptance(
    spec="channels", scenario="rebinding hands the channel over without a restart"
)
async def test_rebinding_stops_here_and_starts_there(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg", config=_config(runs_on=_THIS_MACHINE))

    here = env.runtime_for(_THIS_MACHINE)
    there = env.runtime_for(_OTHER_MACHINE)

    await here.reconcile_once()
    await there.reconcile_once()
    assert here.is_running("tg") is True
    assert there.is_running("tg") is False
    adapter = env.created_adapters[0]

    # An ordinary config edit — no restart, no command reaching another machine.
    await env.resources.update_config(
        resource.uid, await env.bound(_config(runs_on=_OTHER_MACHINE)), actor="test"
    )

    await here.reconcile_once()
    assert here.is_running("tg") is False
    assert adapter.stopped is True
    assert env.processor.binding("tg") is None

    await there.reconcile_once()
    assert there.is_running("tg") is True
    assert len(env.created_adapters) == 2

    await there.dispose()


async def test_a_bound_channel_still_answers_to_reach(env: ChannelEnv) -> None:
    """The binding is a gate beside reach, never a replacement for it.

    A channel bound here and switched off here must stay off: "which machine"
    and "is it live, for which agents" are different questions and both have to
    be answered yes.
    """
    resource = await env.register_channel("tg", config=_config(runs_on=_THIS_MACHINE))
    here = env.runtime_for(_THIS_MACHINE)

    await here.reconcile_once()
    assert here.is_running("tg") is True

    await env.resources.set_enabled(resource.uid, False, actor="test")
    await here.reconcile_once()
    assert here.is_running("tg") is False
