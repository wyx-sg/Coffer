"""A channel is this machine's (spec channels "Keep each channel on the machine
that holds it"): an enabled channel starts here, with no machine to name."""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, uid_of

_TELEGRAM = {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"}


@pytest.mark.acceptance(
    spec="channels", scenario="an enabled channel runs on the machine that holds it"
)
async def test_an_enabled_channel_starts_here(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg", config=dict(_TELEGRAM))

    await env.runtime.reconcile_once()

    assert env.runtime.is_running(uid_of("tg")) is True
    assert len(env.created_adapters) == 1
    status = await env.service.status(resource.uid)
    assert status.running is True
    assert status.diagnostics == ()
