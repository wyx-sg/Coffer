"""A thin sync round: pull, merge outside the tree, stop on any conflict,
guard, check out, push (coffer.application.sync.round_*)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.sync.round_answers import answer, editor_copy
from coffer.application.sync.round_resume import resume
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import Answer, ConflictReason

from .machines import Machine, resource


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an arriving file is written and a deleted one removed"
)
@pytest.mark.acceptance(spec="vault-sync", scenario="a local-only document survives a round")
@pytest.mark.acceptance(spec="vault-sync", scenario="a changed vault converges and pushes")
def test_a_clean_merge_is_applied_and_pushed(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("knowledge/team/a.md", "from the mac\n")
    mini.put("knowledge/team/b.md", "from the mini\n")
    assert mac.round().status is RoundStatus.PUSHED
    got = mini.round()
    assert got.status is RoundStatus.PULLED_AND_PUSHED
    assert [a.path for a in got.applied] == ["knowledge/team/a.md"]
    assert got.snapshot and got.snapshot.startswith("coffer/pre-apply/")
    assert got.with_machines == ("MacBook Pro",)
    assert mac.round().status is RoundStatus.PULLED
    assert mac.disk("knowledge/team/b.md") == b"from the mini\n"
    assert mini.disk("knowledge/team/a.md") == b"from the mac\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="concurrent edits to different parts of one document merge"
)
def test_edits_to_different_parts_of_one_file_merge(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    base = "".join(f"line {i}\n" for i in range(12))
    mac.put("knowledge/team/long.md", base)
    mac.round()
    mini.round()
    mac.put("knowledge/team/long.md", base.replace("line 1\n", "line one\n"))
    mini.put("knowledge/team/long.md", base.replace("line 10\n", "line ten\n"))
    mac.round()
    assert mini.round().status is RoundStatus.PULLED_AND_PUSHED
    merged = mini.disk("knowledge/team/long.md") or b""
    assert b"line one" in merged and b"line ten" in merged


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a real conflict stops the round without touching the vault"
)
def test_any_conflict_stops_the_round_with_vault_and_remote_untouched(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    mac.put("knowledge/team/on-call.md", "Escalate after 30 min.\n")
    mini.put("knowledge/team/on-call.md", "Escalate after 15 min.\n")
    mini.put("knowledge/team/other.md", "unrelated\n")
    mac.round()
    head, tip = mini.repo.head(), mac.repo.head()
    got = mini.round()
    assert got.status is RoundStatus.STOPPED and got.conflicts == 1
    assert mini.repo.head() == head
    assert mini.disk("knowledge/team/on-call.md") == b"Escalate after 15 min.\n"
    assert mini.git.remote_tip("main") == tip
    stop = mini.state.stop()
    assert stop is not None
    (conflict,) = stop.conflicts
    assert conflict.reason is ConflictReason.BOTH_CHANGED
    assert conflict.theirs_machine == "MacBook Pro"
    # Asking again changes nothing while nobody answered.
    assert mini.round().status is RoundStatus.STOPPED


@pytest.mark.acceptance(
    spec="vault-sync", scenario="keeping this machine's version continues the round"
)
def test_keep_mine_continues_the_round_and_the_other_machine_follows(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    mac.put("knowledge/team/on-call.md", "30 min\n")
    mini.put("knowledge/team/on-call.md", "15 min\n")
    mac.round()
    mini.round()
    answer(mini.engine, "knowledge/team/on-call.md", Answer.MINE)
    got = resume(mini.engine, mini.remote, None)
    assert got.status in (RoundStatus.PULLED_AND_PUSHED, RoundStatus.PUSHED)
    assert mini.state.stop() is None
    mac.round()
    assert mac.disk("knowledge/team/on-call.md") == b"15 min\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a hand merge with conflict markers left is refused"
)
def test_a_hand_merge_is_refused_while_markers_are_left(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("knowledge/team/on-call.md", "30 min\n")
    mini.put("knowledge/team/on-call.md", "15 min\n")
    mac.round()
    mini.round()
    path = editor_copy(mini.engine, "knowledge/team/on-call.md")
    marked = Path(path).read_bytes()
    assert b"<<<<<<< Mac mini" in marked and b">>>>>>> MacBook Pro" in marked
    import pytest

    from coffer.application.sync.round_answers import SyncConflictMarkersLeft

    with pytest.raises(SyncConflictMarkersLeft) as caught:
        answer(mini.engine, "knowledge/team/on-call.md", Answer.EDITED)
    assert caught.value.line == 1
    Path(path).write_bytes(b"20 min, a compromise\n")
    answer(mini.engine, "knowledge/team/on-call.md", Answer.EDITED)
    resume(mini.engine, mini.remote, None)
    assert mini.disk("knowledge/team/on-call.md") == b"20 min, a compromise\n"
    mac.round()
    assert mac.disk("knowledge/team/on-call.md") == b"20 min, a compromise\n"


@pytest.mark.acceptance(spec="vault-sync", scenario="a stop is asked again when the remote moves")
def test_a_stop_is_asked_again_when_the_remote_moves(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("knowledge/team/on-call.md", "30 min\n")
    mini.put("knowledge/team/on-call.md", "15 min\n")
    mac.round()
    mini.round()
    first = mini.state.stop()
    mac.put("knowledge/team/on-call.md", "45 min\n")
    mac.round()
    assert mini.round().status is RoundStatus.STOPPED
    second = mini.state.stop()
    assert first and second and first.remote != second.remote


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the same name with a different uid stops the round"
)
def test_the_same_name_with_a_different_uid_is_a_conflict(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("resources/mcp_server/linear.json", resource("mcp_server", "linear", "a" * 32))
    mini.put("resources/mcp_server/linear-work.json", resource("mcp_server", "linear", "b" * 32))
    mac.round()
    got = mini.round()
    assert got.status is RoundStatus.STOPPED
    stop = mini.state.stop()
    assert stop is not None
    reasons = {c.reason for c in stop.conflicts}
    assert ConflictReason.SAME_NAME_DIFFERENT_UID in reasons


@pytest.mark.acceptance(spec="vault-sync", scenario="moving resource files is not a loss")
def test_moving_a_resource_file_is_not_a_loss(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    with mac.writer.begin(mac_meta()) as txn:
        for i in range(25):
            txn.write(f"resources/skill/s{i}.json", resource("skill", f"s{i}", f"{i:032x}"))
    mac.round()
    mini.round()
    with mac.writer.begin(mac_meta()) as txn:
        for i in range(25):
            data = mac.disk(f"resources/skill/s{i}.json")
            assert data is not None
            txn.delete(f"resources/skill/s{i}.json")
            txn.write(
                f"resources/skill/renamed-{i}.json",
                data.replace(b'"name": "s', b'"name": "r'),
            )
    assert mac.round().status is RoundStatus.PUSHED
    assert mini.round().status is RoundStatus.PULLED


def mac_meta():  # type: ignore[no-untyped-def]
    from .machines import USER

    return USER
