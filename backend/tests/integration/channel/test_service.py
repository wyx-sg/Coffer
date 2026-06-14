"""Channel registration + ChannelService (pairing codes, notify) over real SQLite.

Registration goes through the real ResourceService with the channel Kind and
its credential-ref probing; notify goes through a real ChannelRuntime whose
adapter factory produces the recording FakeChannelAdapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.channel.errors import ChannelNotPaired
from coffer.domain.errors import CredentialMissing, ResourceNotFound

from .conftest import ChannelEnv


@pytest.mark.acceptance(spec="009-channels", scenario="register a telegram channel")
async def test_register_telegram_channel_is_listed_with_config_and_audited(
    env: ChannelEnv,
) -> None:
    env.keyring.set("channel/tg/bot-token", "fake-bot-token")
    created = await env.resources.register(
        kind="channel",
        name="tg",
        config={"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"},
        actor="cli",
    )
    assert created.id != 0

    listed = await env.resources.list(kind="channel")
    assert [r.name for r in listed] == ["tg"]
    assert listed[0].enabled is True
    assert listed[0].config["channel_type"] == "telegram"
    assert listed[0].config["bot_token_ref"] == "channel/tg/bot-token"
    assert listed[0].config["default_agent"] == "claude_code"

    entries = await env.audit_entries("resource_created", name="tg")
    assert len(entries) == 1
    assert entries[0].details["config"]["bot_token_ref"] == "channel/tg/bot-token"


@pytest.mark.acceptance(spec="009-channels", scenario="reject a channel with a missing credential")
async def test_register_with_dangling_credential_ref_persists_nothing(env: ChannelEnv) -> None:
    with pytest.raises(CredentialMissing):
        await env.resources.register(
            kind="channel",
            name="tg",
            config={"channel_type": "telegram", "bot_token_ref": "channel/tg/nope"},
            actor="cli",
        )
    assert await env.resources.list(kind="channel") == []
    assert await env.audit_entries("resource_created", name="tg") == []


@pytest.mark.acceptance(spec="009-channels", scenario="issue a pairing code")
async def test_issue_pairing_code_returns_code_with_expiry_and_audits(env: ChannelEnv) -> None:
    await env.register_channel("tg")

    code, expires_at = await env.service.issue_pairing_code("tg", actor="cli")
    assert len(code) == 8
    # The documented unambiguous alphabet (no 0/O/1/I).
    assert set(code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    assert expires_at > datetime.now(tz=UTC)
    assert env.pairing.pending("tg") is True

    entries = await env.audit_entries("channel_pairing_issued", name="tg")
    assert len(entries) == 1
    assert entries[0].details["expires_at"] == expires_at.isoformat()


async def test_issue_pairing_code_for_unknown_channel_raises(env: ChannelEnv) -> None:
    with pytest.raises(ResourceNotFound):
        await env.service.issue_pairing_code("ghost", actor="cli")


@pytest.mark.acceptance(spec="009-channels", scenario="notify delivers to the paired owner")
async def test_notify_sends_via_running_adapter_and_audits(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert len(env.created_adapters) == 1
    adapter = env.created_adapters[0]
    assert adapter.started is True
    await env.pair(resource, chat_id="owner")

    await env.service.notify("tg", "backup finished", actor="cli")

    assert adapter.sent == [("owner", "backup finished")]
    entries = await env.audit_entries("channel_notify_sent", name="tg")
    assert len(entries) == 1
    assert entries[0].details == {"chars": len("backup finished")}


@pytest.mark.acceptance(spec="009-channels", scenario="notify on an unpaired channel fails cleanly")
async def test_notify_without_paired_peer_fails_and_sends_nothing(env: ChannelEnv) -> None:
    await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert len(env.created_adapters) == 1

    with pytest.raises(ChannelNotPaired):
        await env.service.notify("tg", "hello?", actor="cli")

    assert env.created_adapters[0].sent == []
    assert await env.audit_entries("channel_notify_sent", name="tg") == []
