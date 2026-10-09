"""A kind's state as vault documents (spec vault-storage): MCP
capability switches and the engine's settings, each read at ``HEAD`` and
following its owner's rename and delete in the owner's commit — and a
channel's pairings, which stay on this machine beside the channel."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.channel.store_ports import ChannelPeer
from coffer.application.resource_service import ResourceService
from coffer.domain.internal_engine_config import DISTIL, UpkeepSetting
from coffer.domain.resource import Kind
from coffer.domain.vault.layout import StorageClass
from coffer.infrastructure.channel.persistence import ChannelPeerRepo
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from coffer.infrastructure.persistence.internal_engine_repo import VaultInternalEngineConfigRepo
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_repository
from tests.support.vault_stores import derived_db, make_resource_repo


class _Config(BaseModel):
    pass


class _NullAudit:
    async def insert(self, entry: object) -> None:
        return None


def _kinds() -> dict[str, Kind]:
    return {
        "mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_Config),
        "channel": Kind(
            name="channel",
            display_name="Channel",
            config_schema=_Config,
            storage=StorageClass.LOCAL,
        ),
    }


@pytest.mark.acceptance(
    spec="vault-sync", scenario="each shared state area reaches the working tree"
)
async def test_capability_switches_are_a_vault_document_and_seen_times_are_derived() -> None:
    kinds = _kinds()
    repo = make_resource_repo(kinds)
    svc = ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit()))  # type: ignore[arg-type]
    server = await svc.register("mcp_server", "linear", {}, actor="user")
    async with derived_db() as sm:
        prefs = MCPCapabilityPreferenceStore(sm, name_of=repo.name_of)
        repo.add_follower(prefs.documents.follow)
        when = datetime.now(tz=UTC)
        assert await prefs.reconcile(
            server.uid, "tool", ["a", "b"], default_enabled=True, when=when
        ) == ["a", "b"]
        # Nothing switched off: nothing in the vault.
        assert vault_repository().tree("HEAD", "state/") == {}
        off = await prefs.set_enabled(server.uid, "tool", "b", False)
        assert off is not None and off.enabled is False
        path = vault_root() / "state" / "mcp-preferences" / "linear.json"
        assert json.loads(path.read_text()) == {
            "server_uid": server.uid,
            "format_version": 1,
            "disabled": {"tool": ["b"]},
        }
        listed = {p.capability_key: p.enabled for p in await prefs.list_for(server.uid)}
        assert listed == {"a": True, "b": False}
        await svc.delete(server.uid, actor="user")
        assert not path.exists()
        last = vault_repository().log(limit=1)[0]
        assert {p.path for p in last.paths} == {
            "resources/mcp_server/linear.json",
            "state/mcp-preferences/linear.json",
        }


async def test_a_switched_off_capability_never_seen_here_still_reads_off() -> None:
    kinds = _kinds()
    repo = make_resource_repo(kinds)
    svc = ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit()))  # type: ignore[arg-type]
    server = await svc.register("mcp_server", "gh", {}, actor="user")
    async with derived_db() as sm:
        prefs = MCPCapabilityPreferenceStore(sm, name_of=repo.name_of)
        prefs.documents.put(server.uid, "gh", {"disabled": {"tool": ["x"]}}, summary="t")
        found = await prefs.find(server.uid, "tool", "x")
        assert found is not None and found.enabled is False


@pytest.mark.acceptance(
    spec="channels", scenario="a channel stays on the machine that registered it"
)
async def test_a_channel_and_its_pairings_stay_under_local() -> None:
    kinds = _kinds()
    repo = make_resource_repo(kinds)
    svc = ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit()))  # type: ignore[arg-type]
    channel = await svc.register("channel", "tg", {}, actor="user")
    peers = ChannelPeerRepo()
    now = datetime.now(tz=UTC)
    await peers.upsert(ChannelPeer(channel.uid, "dm", "Owner", now, sender_id="s1"))
    await peers.upsert(ChannelPeer(channel.uid, "grp", "Group", now))
    assert (await peers.owner_peer(channel.uid)).chat_id == "dm"  # type: ignore[union-attr]
    assert await peers.sender_ids(channel.uid) == {"s1"}
    await svc.rename(channel.uid, "tg2", actor="user")
    assert (local_root() / "resources/channel/tg2.json").is_file()
    assert channel.uid in json.loads((local_root() / "channel-peers.json").read_text())
    assert not (vault_root() / "resources/channel").exists()
    assert not (vault_root() / "state/channel-peers").exists()
    touched = {c.path for commit in vault_repository().log() for c in commit.paths}
    assert not [p for p in touched if p.startswith(("resources/channel/", "state/channel-"))]
    assert [p.chat_id for p in await peers.list_by_resource(channel.uid)] == ["dm", "grp"]
    await peers.delete_by_chat(channel.uid, "grp")
    await peers.delete_by_chat(channel.uid, "grp")  # already gone: a no-op
    assert [p.chat_id for p in await peers.list_by_resource(channel.uid)] == ["dm"]
    peers.forget(channel.uid)
    assert await peers.list_by_resource(channel.uid) == []


@pytest.mark.acceptance(
    spec="vault-sync", scenario="each shared state area reaches the working tree"
)
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the engine's settings converge and a deletion means the defaults",
)
async def test_engine_settings_are_one_vault_document_and_absent_means_defaults() -> None:
    repo = VaultInternalEngineConfigRepo()
    assert await repo.get() is None
    await repo.set(upkeep={DISTIL: UpkeepSetting(enabled=False, interval_s=60)})
    await repo.set_transcribe_model("hears")
    got = await repo.get()
    assert got is not None and got.transcribe_model == "hears"
    assert got.auto_distil_enabled is False and got.distil_interval_s == 60
    doc = json.loads((vault_root() / "state/settings/internal-engine.json").read_text())
    assert doc["transcribe_model"] == "hears" and "updated_at" not in doc
    assert "updated_at" in json.loads((local_root() / "engine.json").read_text())
    # A key a newer build wrote survives this build's write.
    path = vault_root() / "state/settings/internal-engine.json"
    doc["future"] = True
    path.write_text(json.dumps(doc, indent=2) + "\n")
    from coffer.infrastructure.vault.instance import vault_writer

    vault_writer().settle()
    await repo.set_transcribe_model("whisper")
    assert json.loads(path.read_text())["future"] is True


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="deleting a server's preference document re-enables everything on it",
)
async def test_a_deleted_preference_document_re_enables_the_server() -> None:
    from coffer.domain.vault.writers import WRITER_SYNC, CommitMeta
    from coffer.infrastructure.vault.instance import vault_writer

    kinds = _kinds()
    repo = make_resource_repo(kinds)
    svc = ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit()))  # type: ignore[arg-type]
    linear = await svc.register("mcp_server", "linear", {}, actor="user")
    github = await svc.register("mcp_server", "github", {}, actor="user")
    async with derived_db() as sm:
        prefs = MCPCapabilityPreferenceStore(sm, name_of=repo.name_of)
        when = datetime.now(tz=UTC)
        for server in (linear, github):
            await prefs.reconcile(server.uid, "tool", ["a", "b"], default_enabled=True, when=when)
            await prefs.set_enabled(server.uid, "tool", "b", False)
        # Another machine re-enabled everything on linear: its document goes.
        vault_writer().delete_file(
            "state/mcp-preferences/linear.json",
            meta=CommitMeta(writer=WRITER_SYNC, operation="sync", summary="merged"),
        )
        on = {p.capability_key: p.enabled for p in await prefs.list_for(linear.uid)}
        assert on == {"a": True, "b": True}
        still = {p.capability_key: p.enabled for p in await prefs.list_for(github.uid)}
        assert still == {"a": True, "b": False}
        assert "state/mcp-preferences/linear.json" not in vault_repository().tree("HEAD", "state/")
