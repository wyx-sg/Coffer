"""The sync service over real rounds: recorded rounds and the status, a stop
answered file by file, the editor copy, a hold confirmed and restored, a
join's differing files, and rolling a round back
(ADR sync-applies-clean-merges-and-stops-on-any-conflict)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.sync.round_answers import SyncConflictMarkersLeft
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import Answer, HoldDirection

from .harness import fleet, joined

DOC = "knowledge/team/on-call.md"


@pytest.mark.acceptance(spec="vault-sync", scenario="every round is recorded with what it moved")
def test_a_round_is_recorded_and_the_status_shows_what_waits_to_push(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put("knowledge/team/deploy.md", "Deploy on Tuesdays.\n")
    waiting = mac.run(mac.service.status()).waiting
    assert [c.path for w in waiting for c in w.changes] == ["knowledge/team/deploy.md"]
    assert waiting[0].writer == "user"

    pushed = mac.round()
    assert pushed.status is RoundStatus.PUSHED
    assert pushed.id is not None
    assert mac.run(mac.service.status()).waiting == ()

    pulled = mini.round()
    assert pulled.status is RoundStatus.PULLED
    assert [a.path for a in pulled.applied] == ["knowledge/team/deploy.md"]
    assert mini.disk("knowledge/team/deploy.md") == b"Deploy on Tuesdays.\n"
    status = mini.run(mini.service.status())
    assert status.areas.knowledge_documents == 2
    assert status.machines == 2
    assert status.last_round is not None and status.last_round.id == pulled.id
    page = mini.run(mini.service.rounds(limit=2))
    assert page.rounds[0].id == pulled.id
    assert page.total == len(mini.history.rows)
    assert mini.run(mini.service.round(pulled.id)).status is RoundStatus.PULLED  # type: ignore[arg-type]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a real conflict stops the round without touching the vault"
)
def test_a_conflict_stops_the_round_and_each_file_is_answered(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")

    stopped = mini.round()
    assert stopped.status is RoundStatus.STOPPED
    assert stopped.conflicts == 1
    assert mini.disk(DOC) == b"Mini rotates on Fridays.\n"
    shown = mini.run(mini.service.stopped())
    assert shown is not None
    (f,) = shown.files
    assert f.file.path == DOC and f.file.area == "knowledge"
    assert f.file.theirs_machine == "Mac"
    assert f.file.ours_time and f.file.theirs_time
    versions = mini.run(mini.service.file_versions(DOC))
    assert versions.ours == "Mini rotates on Fridays.\n"
    assert "+Mac rotates on Mondays." in versions.take_theirs
    mini.run(mini.service.answer(DOC, Answer.THEIRS))
    done = mini.run(mini.service.continue_round())
    assert done.status in (RoundStatus.PULLED, RoundStatus.PULLED_AND_PUSHED)
    assert mini.disk(DOC) == b"Mac rotates on Mondays.\n"
    assert mini.run(mini.service.stopped()) is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a hand merge with conflict markers left is refused"
)
def test_a_hand_merge_is_refused_while_markers_are_left(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    mini.round()

    where = Path(mini.run(mini.service.open_editor(DOC)))
    assert b"<<<<<<<" in where.read_bytes()
    assert mini.repo.root not in where.parents
    with pytest.raises(SyncConflictMarkersLeft) as refused:
        mini.run(mini.service.answer(DOC, Answer.EDITED))
    assert "Line 1" in str(refused.value)
    assert mini.run(mini.service.stopped()).files[0].editor_path == str(where)  # type: ignore[union-attr]

    where.write_text("Both rotate: Mondays and Fridays.\n")
    mini.run(mini.service.answer(DOC, Answer.EDITED))
    mini.run(mini.service.continue_round())
    assert mini.disk(DOC) == b"Both rotate: Mondays and Fridays.\n"
    assert mac.round().status is RoundStatus.PULLED
    assert mac.disk(DOC) == b"Both rotate: Mondays and Fridays.\n"


def _bulk(n: int) -> list[str]:
    return [f"knowledge/bulk/note-{i:02}.md" for i in range(n)]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an oversized deletion is held for confirmation"
)
def test_a_mass_deletion_is_held_both_ways_and_answered(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    for path in _bulk(25):
        mac.put(path, f"{path}\n")
    mac.round()
    mini.round()
    mac.remove(*_bulk(25))

    held = mac.round()
    assert held.status is RoundStatus.HELD
    shown = mac.run(mac.service.stopped())
    assert shown is not None and shown.stop.hold is not None
    assert shown.stop.hold.direction is HoldDirection.OUTGOING
    (group,) = shown.groups
    assert (group.folder, len(group.paths), group.total) == ("knowledge/bulk", 25, 25)
    assert shown.machines == ("Mac",)
    mac.run(mac.service.confirm_hold())
    assert mac.run(mac.service.continue_round()).status is RoundStatus.PUSHED

    incoming = mini.round()
    assert incoming.status is RoundStatus.HELD
    shown = mini.run(mini.service.stopped())
    assert shown.stop.hold.direction is HoldDirection.INCOMING  # type: ignore[union-attr]
    assert shown.machines == ("Mac",)  # type: ignore[union-attr]
    mini.run(mini.service.restore_hold(actor="user"))
    kept = mini.run(mini.service.continue_round())
    # Nothing new arrives here — the files are this machine's again — and
    # they go back to the remote.
    assert kept.status is RoundStatus.PUSHED
    assert len(kept.pushed) == 25
    assert all(mini.disk(p) is not None for p in _bulk(25))
    mac.round()
    assert all(mac.disk(p) is not None for p in _bulk(25))


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a new machine takes the union and deletes nothing"
)
def test_a_join_leaves_differing_files_until_the_person_chooses(tmp_path: Path) -> None:
    mac, mini = fleet(tmp_path, "Mac", "Mini")
    mac.put("knowledge/a.md", "A from the Mac\n")
    mac.run(mac.service.join())
    mini.put("knowledge/a.md", "A from the Mini\n")
    mini.put("knowledge/b.md", "B\n")

    preview = mini.run(mini.service.join_preview())
    assert preview.differ == ("knowledge/a.md",)
    joined_round = mini.run(mini.service.join())
    assert joined_round.status is RoundStatus.JOINED
    assert mini.disk("knowledge/a.md") == b"A from the Mini\n"
    (choice,) = mini.run(mini.service.join_choices())
    assert choice.path == "knowledge/a.md"

    remaining = mini.run(mini.service.choose([("knowledge/a.md", Answer.MINE)], actor="user"))
    assert remaining == ()
    mini.round()
    mac.round()
    assert mac.disk("knowledge/a.md") == b"A from the Mini\n"
    assert mac.disk("knowledge/b.md") == b"B\n"


@pytest.mark.acceptance(spec="vault-sync", scenario="a round can be rolled back")
def test_a_round_is_rolled_back_and_later_edits_are_kept(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Rotates on Tuesdays.\n")
    mac.put("knowledge/team/pager.md", "Pager v1\n")
    mac.round()
    got = mini.round()
    assert got.status is RoundStatus.PULLED
    mini.put("knowledge/team/pager.md", "Pager v2, edited after\n")

    plan = mini.run(mini.service.rollback_plan(got.id))  # type: ignore[arg-type]
    assert [(c.path, c.status) for c in plan.reverses] == [(DOC, "modified")]
    assert plan.kept == ("knowledge/team/pager.md",)
    assert plan.snapshot_time is not None

    rolled = mini.run(mini.service.rollback(got.id, actor="user"))  # type: ignore[arg-type]
    assert rolled.status is RoundStatus.ROLLED_BACK
    assert mini.disk(DOC) == b"Primary on-call rotates every Monday.\n"
    assert mini.disk("knowledge/team/pager.md") == b"Pager v2, edited after\n"
    mini.round()
    mac.round()
    assert mac.disk(DOC) == b"Primary on-call rotates every Monday.\n"
