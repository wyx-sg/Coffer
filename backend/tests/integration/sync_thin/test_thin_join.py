"""Joining a remote: empty, new (union), returning (base from the descriptor)."""

from __future__ import annotations

from pathlib import Path

from coffer.application.sync.round_answers import choose_join
from coffer.application.sync.round_join import join, preview
from coffer.domain.sync.joins import JoinKind
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import Answer, ConflictReason

from .machines import Machine, resource


def test_the_first_machine_pushes_the_whole_vault(mac: Machine) -> None:
    mac.put("knowledge/team/a.md", "a\n")
    shown = preview(mac.engine, mac.remote, None)
    assert shown.kind is JoinKind.EMPTY and shown.pushed_files >= 1
    assert join(mac.engine, mac.remote, None).status is RoundStatus.PUSHED
    assert mac.git.remote_tip("main") == mac.repo.head()


def test_a_timer_round_never_joins_on_its_own(mac: Machine) -> None:
    assert mac.round().status is RoundStatus.JOIN_REQUIRED


def test_a_new_machine_takes_the_union_and_leaves_differing_files_alone(
    mac: Machine, mini: Machine
) -> None:
    mac.put("knowledge/team/on-call.md", "escalate after 30 min\n")
    mac.put("knowledge/team/mac-only.md", "mac\n")
    join(mac.engine, mac.remote, None)
    mini.put("knowledge/team/on-call.md", "escalate after 15 min\n")
    mini.put("knowledge/team/mini-only.md", "mini\n")
    shown = preview(mini.engine, mini.remote, None)
    assert shown.kind is JoinKind.NEW
    assert shown.differ == ("knowledge/team/on-call.md",)
    assert shown.pulled_files == 1 and shown.pushed_files == 1
    got = join(mini.engine, mini.remote, None)
    assert got.status is RoundStatus.JOINED and got.held == 1
    assert mini.disk("knowledge/team/mac-only.md") == b"mac\n"
    assert mini.disk("knowledge/team/on-call.md") == b"escalate after 15 min\n"
    # The differing file is not pushed until chosen, and never settled.
    assert mini.writer.pending() == {}
    mac.round()
    assert mac.disk("knowledge/team/mini-only.md") == b"mini\n"
    assert mac.disk("knowledge/team/on-call.md") == b"escalate after 30 min\n"
    choose_join(mini.engine, "knowledge/team/on-call.md", Answer.MINE, actor="user")
    mini.round()
    mac.round()
    assert mac.disk("knowledge/team/on-call.md") == b"escalate after 15 min\n"


def test_taking_theirs_for_a_differing_file_replaces_it_here(mac: Machine, mini: Machine) -> None:
    mac.put("knowledge/team/x.md", "theirs\n")
    join(mac.engine, mac.remote, None)
    mini.put("knowledge/team/x.md", "mine\n")
    join(mini.engine, mini.remote, None)
    choose_join(mini.engine, "knowledge/team/x.md", Answer.THEIRS, actor="user")
    assert mini.disk("knowledge/team/x.md") == b"theirs\n"
    assert mini.writer.pending() == {}


def test_a_join_with_the_same_name_and_a_different_uid_stops(mac: Machine, mini: Machine) -> None:
    mac.put("resources/mcp_server/linear.json", resource("mcp_server", "linear", "a" * 32))
    join(mac.engine, mac.remote, None)
    mini.put("resources/mcp_server/linear-2.json", resource("mcp_server", "linear", "b" * 32))
    got = join(mini.engine, mini.remote, None)
    assert got.status is RoundStatus.STOPPED
    stop = mini.state.stop()
    assert stop and stop.conflicts[0].reason is ConflictReason.SAME_NAME_DIFFERENT_UID


def test_a_returning_machine_merges_from_the_base_in_its_descriptor(
    tmp_path: Path, remote: SyncRemote, pair: tuple[Machine, Machine]
) -> None:
    mac, mini = pair
    for i in range(10):  # large enough that one deletion is not a mass deletion
        mac.put(f"knowledge/team/filler-{i}.md", f"filler {i}\n")
    mac.put("knowledge/team/keep.md", "keep\n")
    mac.put("knowledge/team/drop.md", "drop\n")
    mac.round()
    mini.round()
    mac.round()
    # The mini is reinstalled: a fresh vault holding its files as they were,
    # minus one it deleted while offline.
    again = Machine(tmp_path / "mini-again", "Mac mini", remote)
    kept = ["knowledge/team/on-call.md", "knowledge/team/keep.md"]
    kept += [f"knowledge/team/filler-{i}.md" for i in range(10)]
    for path in kept:
        data = mini.disk(path)
        assert data is not None
        again.put(path, data)
    shown = preview(again.engine, remote, None)
    assert shown.kind is JoinKind.RETURNING and shown.base
    assert "knowledge/team/drop.md" in shown.deleted
    got = join(again.engine, remote, None)
    assert got.status in (RoundStatus.JOINED, RoundStatus.PUSHED, RoundStatus.PULLED_AND_PUSHED)
    mac.round()
    assert mac.disk("knowledge/team/drop.md") is None
    assert mac.disk("knowledge/team/keep.md") == b"keep\n"
