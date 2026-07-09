"""Channel pairing state syncs as a state area (spec 010 slice 4, ADR-043)."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from pydantic import BaseModel

from coffer.application.channel.ports import ChannelPeer
from coffer.application.channel.sync_state import ChannelPeerSyncState
from coffer.domain.resource import Kind
from coffer.infrastructure.channel.persistence import ChannelPeerRepo

from .test_two_machine_sync import _make_machine


class _ChannelCfg(BaseModel):
    channel_type: str = "telegram"
    bot_token_ref: str = ""
    runs_on: str | None = None


@pytest_asyncio.fixture
async def remote(tmp_path):  # type: ignore[no-untyped-def]
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _kinds() -> dict[str, Kind]:
    return {"channel": Kind(name="channel", display_name="Channel", config_schema=_ChannelCfg)}


def _providers(resources, sm):  # type: ignore[no-untyped-def]
    return [ChannelPeerSyncState(resources, ChannelPeerRepo(sm))]


@pytest.mark.acceptance(spec="010-sync", scenario="channel pairing state syncs with the vault")
async def test_pairing_identity_round_trips(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine(
        "A",
        tmp_path / "A",
        remote,
        create_key=True,
        kinds=_kinds(),
        state_providers_factory=_providers,
    )
    chan = await a.resources.register(
        "channel",
        "tg",
        {"channel_type": "telegram", "bot_token_ref": "r", "runs_on": "M-A"},
        "test",
    )
    peers_a = ChannelPeerRepo(a.sm)
    await peers_a.upsert(
        ChannelPeer(
            resource_id=chan.id,
            chat_id="12345",
            display_name="Owner",
            paired_at=datetime(2026, 7, 1, tzinfo=UTC),
            active_conversation_id="conv-local-a",
            sender_id="777",
            preferred_agent="claude_code",
        )
    )
    await a.service.run()

    b = await _make_machine(
        "B",
        tmp_path / "B",
        remote,
        create_key=True,
        kinds=_kinds(),
        state_providers_factory=_providers,
    )
    await b.service.run()

    # B has the channel AND its pairing identity — no re-pairing needed.
    chan_b = next(r for r in await b.resources.list() if r.name == "tg")
    peers_b = ChannelPeerRepo(b.sm)
    peer = await peers_b.get_by_chat(chan_b.id, "12345")
    assert peer is not None
    assert peer.display_name == "Owner"
    assert peer.sender_id == "777"
    assert peer.preferred_agent == "claude_code"
    # The machine-local conversation pointer did NOT travel.
    assert peer.active_conversation_id is None

    # Re-import on A preserves A's local conversation pointer.
    await b.service.run()
    await a.service.run()
    peer_a = await peers_a.get_by_chat(chan.id, "12345")
    assert peer_a is not None
    assert peer_a.active_conversation_id == "conv-local-a"
