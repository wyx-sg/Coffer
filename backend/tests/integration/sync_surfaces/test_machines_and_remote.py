"""Machines, the remote, the key, and what a round refuses to do
(ADR sync-applies-clean-merges-and-stops-on-any-conflict; spec vault-sync
"Publish one descriptor per machine")."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from coffer.application.sync.attention import SyncAttentionSource
from coffer.application.sync.worker import SyncWorker
from coffer.domain.credential_errors import SecretBindingPending
from coffer.domain.sync.errors import (
    CannotRetireSelf,
    MasterKeyFileInvalid,
    SyncMachineNotFound,
)
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.infrastructure.sync.cloud_folder import synchroniser_of
from tests.integration.sync_thin.machines import bare_remote

from .harness import Box, fleet, joined


def _remote_files(url: str, prefix: str) -> set[str]:
    done = subprocess.run(
        ["git", "--git-dir", url, "ls-tree", "-r", "--name-only", "main", prefix],
        capture_output=True,
        check=True,
    )
    return set(done.stdout.decode().split())


@pytest.mark.acceptance(spec="vault-sync", scenario="renaming a machine costs nothing")
@pytest.mark.acceptance(spec="vault-sync", scenario="a retired machine leaves the registry with its descriptor")
@pytest.mark.acceptance(spec="vault-sync", scenario="a round publishes this machine's descriptor and no other")
def test_machines_are_listed_renamed_and_retired(tmp_path: Path) -> None:
    mac, mini, _old = joined(tmp_path, "Mac", "Mini", "Old")
    mini.round()
    views = mini.run(mini.service.machines())
    assert views[0].descriptor.machine_id == "mini"
    assert {v.descriptor.name for v in views} == {"Mac", "Mini", "Old"}
    assert all(v.key_matches for v in views)
    assert all(v.descriptor.coffer_version == "0.9.0" for v in views)

    renamed = mini.run(mini.service.rename_self("Studio", actor="user"))
    assert renamed.descriptor.name == "Studio"
    mini.round()
    mac.round()
    assert "Studio" in {v.descriptor.name for v in mac.run(mac.service.machines())}

    with pytest.raises(CannotRetireSelf):
        mini.run(mini.service.retire_machine("mini", actor="user"))
    with pytest.raises(SyncMachineNotFound):
        mini.run(mini.service.retire_machine("nobody", actor="user"))

    # The remote moves on before the retirement is pushed: the merge must
    # keep the deliberate deletion rather than take the remote's copy back.
    mac.put("knowledge/team/new.md", "New.\n")
    mac.round()
    mini.run(mini.service.retire_machine("old", actor="user"))
    assert mini.repo.read("HEAD", "machines/old.json") is None
    assert mini.repo.read("HEAD", "machines/mac.json") is not None
    mini.round()
    assert _remote_files(mini.url, "machines") == {"machines/mac.json", "machines/mini.json"}
    mac.round()
    assert {v.descriptor.machine_id for v in mac.run(mac.service.machines())} == {"mac", "mini"}


@pytest.mark.acceptance(spec="vault-sync", scenario="a descriptor publishes the pointer this machine reached")
@pytest.mark.acceptance(spec="vault-sync", scenario="a descriptor carries what the machines table shows")
@pytest.mark.acceptance(spec="vault-sync", scenario="an arriving plugin inventory writes nothing into an agent")
def test_a_descriptor_carries_the_fields_and_the_plugin_inventory(tmp_path: Path) -> None:
    from coffer.domain.sync.machine import AgentInventory, Plugin

    (mac,) = joined(tmp_path, "Mac")
    mac.host.set_agents([AgentInventory("codex", "codex", (Plugin("linear", "Linear"),))])
    mac.put("knowledge/x.md", "x\n")
    mac.round()
    doc = json.loads(mac.repo.read("HEAD", "machines/mac.json") or b"{}")
    assert doc["format_version"] == 1
    assert doc["name"] == "Mac" and doc["os"] and doc["hostname"] == "mac.local"
    assert doc["last_round_at"] and doc["last_converged_commit"]
    assert doc["agents"][0]["type"] == "codex"
    assert doc["agents"][0]["plugins"][0]["id"] == "linear"


@pytest.mark.acceptance(spec="vault-sync", scenario="an invalid hand edit on a path the round changes is never overwritten")
def test_an_invalid_hand_edit_on_a_path_the_round_changes_is_never_overwritten(
    tmp_path: Path,
) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini", validate=True)
    doc = "resources/mcp_server/linear.json"
    mac.put(doc, '{"url": "https://mcp.linear.app"}\n')
    mac.round()
    mini.round()
    mac.put(doc, '{"url": "https://mcp.linear.app/v2"}\n')
    mac.round()
    (mini.repo.root / doc).write_text('{"url": "https://mcp.linear.app", oops\n')

    got = mini.round()
    assert got.status is RoundStatus.WAITING_ON_EDIT
    assert got.path == doc
    assert (mini.repo.root / doc).read_text() == '{"url": "https://mcp.linear.app", oops\n'
    assert mini.repo.read("HEAD", doc) == b'{"url": "https://mcp.linear.app"}\n'


@pytest.mark.acceptance(spec="vault-sync", scenario="a vault in a synchronised folder pauses")
@pytest.mark.parametrize("marker", [".stfolder", ".dropbox"])
def test_a_vault_in_a_synchronised_folder_pauses(tmp_path: Path, marker: str) -> None:
    root = tmp_path / "Sync" / "mac"
    (tmp_path / "Sync").mkdir()
    (tmp_path / "Sync" / marker).mkdir()
    box = Box(
        root,
        "mac",
        "Mac",
        str(bare_remote(tmp_path)),
        cloud=lambda: synchroniser_of(root / "vault", home=tmp_path / "home"),
    )
    got = box.round()
    assert got.status is RoundStatus.PAUSED_CLOUD_FOLDER
    status = box.run(box.service.status())
    assert status.synchroniser in ("Syncthing", "Dropbox")
    assert status.problem is not None and status.problem.kind == "cloud_folder"


@pytest.mark.acceptance(spec="vault-sync", scenario="a vault in a synchronised folder pauses")
def test_icloud_and_file_provider_roots_are_synchronisers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "coffer" / "vault"
    drive = home / "Library" / "CloudStorage" / "GoogleDrive-me" / "vault"
    assert synchroniser_of(icloud, home=home) == "iCloud Drive"
    assert synchroniser_of(drive, home=home) == "a cloud drive"
    assert synchroniser_of(home / ".coffer" / "vault", home=home) is None


@pytest.mark.acceptance(spec="vault-sync", scenario="a curation pass and a converge round do not overlap")
def test_the_worker_never_runs_a_round_while_curation_holds_the_lock(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")

    async def scenario() -> tuple[int, int, int]:
        worker = SyncWorker(mac.service, start_delay_s=0, idle_poll_s=0.01)
        before = await mac.history.count()
        async with mac.service.lock:  # a curation pass is running
            tick = asyncio.create_task(worker.tick())
            await asyncio.sleep(0.5)
            during = await mac.history.count()
            assert not tick.done()
        await tick
        return before, during, await mac.history.count()

    before, during, after = mac.run(scenario())
    assert during == before
    assert after == before + 1


@pytest.mark.acceptance(spec="vault-sync", scenario="a paused remote runs no round and asks for nothing")
def test_the_worker_does_not_run_while_the_remote_is_paused(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    mac.run(mac.service.pause(False))
    worker = SyncWorker(mac.service, start_delay_s=0, idle_poll_s=0.01)
    before = len(mac.history.rows)
    assert mac.run(worker.tick()) == 0.01
    assert len(mac.history.rows) == before
    assert mac.run(mac.service.status()).next_round_at is None


@pytest.mark.acceptance(spec="vault-sync", scenario="an ordinary round on a machine without a pointer still detects the join")
@pytest.mark.acceptance(spec="vault-sync", scenario="a remote is checked before it is saved")
def test_a_remote_is_checked_set_and_cleared(tmp_path: Path) -> None:
    (mac,) = fleet(tmp_path, "Mac")
    assert mac.run(mac.service.check_remote(mac.url, "main", None)).result == "empty"
    mac.run(mac.service.join())
    found = mac.run(mac.service.check_remote(mac.url, "main", None))
    assert (found.result, found.layout) == ("vault", 3)
    gone = mac.run(mac.service.check_remote(str(tmp_path / "nowhere.git"), "main", None))
    assert gone.result in ("unreachable", "auth_failed", "failed") and gone.detail

    other = str(bare_remote(tmp_path / "other"))
    mac.run(mac.service.set_remote(SyncRemote(url=other, include_secret=True)))
    assert mac.remotes.get() == SyncRemote(url=other, include_secret=True)
    assert not mac.state.joined()
    assert mac.repo.carries_secret
    assert mac.round().status is RoundStatus.JOIN_REQUIRED

    assert mac.run(mac.service.clear_remote()) is True
    assert mac.remotes.get() is None
    assert mac.run(mac.service.clear_remote()) is False


@pytest.mark.acceptance(spec="vault-sync", scenario="a token waiting for approval is a sign-in problem")
def test_a_token_waiting_for_approval_is_a_recorded_sign_in_problem(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    mac.remotes.put(SyncRemote(url=mac.url, credential_ref="sync/github-token"))
    mac.token.error = SecretBindingPending(["a1"], ["sync"])
    got = mac.round()
    assert got.status is RoundStatus.AUTH_FAILED
    assert "sync/github-token" in (got.detail or "")
    problem = mac.run(mac.service.status()).problem
    assert problem is not None
    assert (problem.kind, problem.credential_ref) == ("auth_failed", "sync/github-token")
    items = mac.run(SyncAttentionSource(sync=mac.service).items())
    assert [i.reason_code for i in items] == ["sync_auth_failed"]


@pytest.mark.acceptance(spec="vault-sync", scenario="the attention list names what a round waits for")
def test_attention_names_a_stop_and_a_join_choice(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put("knowledge/team/on-call.md", "Mac\n")
    mac.round()
    mini.put("knowledge/team/on-call.md", "Mini\n")
    mini.round()
    items = mini.run(SyncAttentionSource(sync=mini.service).items())
    assert [i.reason_code for i in items] == ["sync_conflicts"]
    assert items[0].action.path == "/api/v1/sync/stop"


@pytest.mark.acceptance(spec="vault-sync", scenario="credentials this machine cannot decrypt are reported locked")
def test_a_key_import_is_checked_and_answers_the_refs_still_locked(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    with pytest.raises(MasterKeyFileInvalid):
        mac.run(mac.service.import_key("   "))
    with pytest.raises(MasterKeyFileInvalid):
        mac.run(mac.service.import_key("not-a-key"))
    mac.secrets.locked = ["channel/seatalk/app-secret"]
    assert mac.run(mac.service.import_key("ok-key")) == ["channel/seatalk/app-secret"]
    assert mac.service.key_fingerprint() == "abc123abc123"
    assert mac.audit.events[-1][0] == "master_key_imported"
