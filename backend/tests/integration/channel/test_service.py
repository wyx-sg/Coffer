"""Channel registration + ChannelService (pairing codes, notify) over real SQLite.

Registration goes through the real ResourceService with the channel Kind and
its credential-ref probing; notify goes through a real ChannelRuntime whose
adapter factory produces the recording FakeChannelAdapter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel.store_ports import ChannelPeer
from coffer.domain.channel.errors import ChannelNotPaired
from coffer.domain.errors import CredentialMissing, ResourceNotFound

from .conftest import ChannelEnv


@pytest.mark.acceptance(spec="channels", scenario="register a telegram channel")
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
    # No agent named at create: ``default_agent`` is a reference to an agent
    # resource and there is no constant that could stand for one, so a channel
    # registered without one is bound to nobody until the owner picks.
    assert listed[0].config["default_agent"] is None

    entries = await env.audit_entries("resource_created", created)
    assert len(entries) == 1
    assert entries[0].details["config"]["bot_token_ref"] == "channel/tg/bot-token"


@pytest.mark.acceptance(spec="channels", scenario="reject a channel with a missing credential")
async def test_register_with_dangling_credential_ref_persists_nothing(env: ChannelEnv) -> None:
    with pytest.raises(CredentialMissing):
        await env.resources.register(
            kind="channel",
            name="tg",
            config={"channel_type": "telegram", "bot_token_ref": "channel/tg/nope"},
            actor="cli",
        )
    assert await env.resources.list(kind="channel") == []
    assert await env.audit_entries("resource_created") == []


@pytest.mark.acceptance(spec="channels", scenario="issue a pairing code")
async def test_issue_pairing_code_returns_code_with_expiry_and_audits(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")

    code, expires_at, pair_url = await env.service.issue_pairing_code(resource.uid, actor="cli")
    # No adapter is running, so there is no bot username to build a link from —
    # the typed code is the only way in and must still be issued.
    assert pair_url == ""
    assert len(code) == 8
    # The documented unambiguous alphabet (no 0/O/1/I).
    assert set(code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    assert expires_at > datetime.now(tz=UTC)
    assert env.pairing.pending("tg") is True

    entries = await env.audit_entries("channel_pairing_issued", resource)
    assert len(entries) == 1
    assert entries[0].details["expires_at"] == expires_at.isoformat()


async def test_issue_pairing_code_for_unknown_channel_raises(env: ChannelEnv) -> None:
    with pytest.raises(ResourceNotFound):
        await env.service.issue_pairing_code("uid-of-a-ghost", actor="cli")


@pytest.mark.acceptance(spec="channels", scenario="notify delivers to the paired owner")
async def test_notify_sends_via_running_adapter(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert len(env.created_adapters) == 1
    adapter = env.created_adapters[0]
    assert adapter.started is True
    await env.pair(resource, chat_id="owner")

    await env.service.notify(resource.uid, "backup finished", actor="cli")

    assert adapter.sent == [("owner", "backup finished")]


async def test_notify_goes_to_the_owner_dm_not_to_a_group(env: ChannelEnv) -> None:
    """The bug: ``notify`` read "the channel's peer" through a query with no
    ``ORDER BY``, so whether a private notification reached the owner or a
    group chat depended on what SQLite happened to return first.

    A channel holds one peer row per chat it is paired to. The owner chat is
    the earliest pairing — a group can only be added to a channel whose DM
    already works.
    """
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    adapter = env.created_adapters[0]

    # Paired group-first, so insertion order disagrees with pairing order.
    await env.peers.upsert(
        ChannelPeer(
            resource_id=resource.id,
            chat_id="team-group",
            display_name="Team",
            paired_at=datetime.now(tz=UTC),
        )
    )
    await env.peers.upsert(
        ChannelPeer(
            resource_id=resource.id,
            chat_id="owner-dm",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC) - timedelta(days=2),
        )
    )

    await env.service.notify(resource.uid, "your backup failed", actor="cli")

    assert adapter.sent == [("owner-dm", "your backup failed")]


async def test_notify_can_name_a_paired_chat_explicitly(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    adapter = env.created_adapters[0]
    await env.pair(resource, chat_id="owner-dm")
    await env.peers.upsert(
        ChannelPeer(
            resource_id=resource.id,
            chat_id="team-group",
            display_name="Team",
            paired_at=datetime.now(tz=UTC),
        )
    )

    await env.service.notify(resource.uid, "deploy done", actor="cli", chat_id="team-group")

    assert adapter.sent == [("team-group", "deploy done")]


async def test_notify_refuses_a_chat_this_channel_is_not_paired_to(env: ChannelEnv) -> None:
    """Otherwise ``chat_id`` would be a way to message an arbitrary chat id
    through a channel that has no relationship with it."""
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    adapter = env.created_adapters[0]
    await env.pair(resource, chat_id="owner-dm")

    with pytest.raises(ChannelNotPaired):
        await env.service.notify(resource.uid, "psst", actor="cli", chat_id="someone-else")

    assert adapter.sent == []


@pytest.mark.acceptance(spec="channels", scenario="notify on an unpaired channel fails cleanly")
async def test_notify_without_paired_peer_fails_and_sends_nothing(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert len(env.created_adapters) == 1

    with pytest.raises(ChannelNotPaired):
        await env.service.notify(resource.uid, "hello?", actor="cli")

    assert env.created_adapters[0].sent == []
