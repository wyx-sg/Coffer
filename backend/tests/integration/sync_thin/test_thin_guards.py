"""The breaker in both directions, snapshots and rollback, credentials and
layouts (coffer.application.sync.round_*)."""

from __future__ import annotations

import base64
import struct
from pathlib import Path

import pytest

from coffer.application.sync.round_answers import confirm_hold, restore_held
from coffer.application.sync.round_resume import resume
from coffer.application.sync.round_rollback import SyncNothingToRollBack, plan, rollback
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import HoldDirection
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.remote import RemoteProblem, classify

from .machines import USER, Machine, bare_remote, remote_ref


def _many(m: Machine, n: int, prefix: str = "knowledge/team/doc") -> None:
    with m.writer.begin(USER) as txn:
        for i in range(n):
            txn.write(f"{prefix}-{i}.md", f"document {i}\n".encode(), Expect.ABSENT)


def test_a_local_mass_deletion_is_held_before_it_is_pushed(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    _many(mac, 25)
    mac.round()
    mini.round()
    mac.remove(*(f"knowledge/team/doc-{i}.md" for i in range(25)))
    tip = remote_ref(mac.remote)
    got = mac.round()
    assert got.status is RoundStatus.HELD and got.held == 25
    assert remote_ref(mac.remote) == tip
    stop = mac.state.stop()
    assert stop and stop.hold and stop.hold.direction is HoldDirection.OUTGOING
    confirm_hold(mac.engine)
    assert resume(mac.engine, mac.remote, None).status is RoundStatus.PUSHED


def test_an_incoming_mass_deletion_is_held_and_can_be_restored(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    _many(mac, 25)
    mac.round()
    mini.round()
    mac.remove(*(f"knowledge/team/doc-{i}.md" for i in range(25)))
    mac.round()
    confirm_hold(mac.engine)
    resume(mac.engine, mac.remote, None)
    got = mini.round()
    assert got.status is RoundStatus.HELD
    stop = mini.state.stop()
    assert stop and stop.hold and stop.hold.direction is HoldDirection.INCOMING
    assert mini.disk("knowledge/team/doc-3.md") == b"document 3\n"
    restore_held(mini.engine, actor="user")
    after = resume(mini.engine, mini.remote, None)
    assert after.status in (RoundStatus.PULLED_AND_PUSHED, RoundStatus.PUSHED)
    assert mini.disk("knowledge/team/doc-3.md") == b"document 3\n"
    mac.round()
    assert mac.disk("knowledge/team/doc-3.md") == b"document 3\n"


def test_a_round_can_be_rolled_back_keeping_later_edits(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    _many(mac, 10)  # an area large enough that one deletion is not a mass deletion
    mac.round()
    mini.round()
    mac.put("knowledge/team/a.md", "a from mac\n")
    mac.put("knowledge/team/b.md", "b from mac\n")
    mac.round()
    pulled = mini.round()
    assert pulled.applied
    mini.put("knowledge/team/b.md", "b edited on mini afterwards\n")
    shown = plan(mini.engine, pulled)
    assert [c.path for c in shown.reverses] == ["knowledge/team/a.md"]
    assert shown.kept == ("knowledge/team/b.md",)
    done = rollback(mini.engine, pulled, actor="user")
    assert done.status is RoundStatus.ROLLED_BACK
    assert mini.disk("knowledge/team/a.md") is None
    assert mini.disk("knowledge/team/b.md") == b"b edited on mini afterwards\n"
    newest = mini.repo.log(limit=1)[0]
    assert newest.meta.operation == "restore" and newest.meta.restored_from
    mini.round()
    mac.round()
    assert mac.disk("knowledge/team/a.md") is None


def test_a_round_that_applied_nothing_has_nothing_to_roll_back(
    pair: tuple[Machine, Machine],
) -> None:
    mac, _mini = pair
    mac.put("knowledge/team/x.md", "x\n")
    pushed = mac.round()
    with pytest.raises(SyncNothingToRollBack):
        plan(mac.engine, pushed)


def _fernet(when: int, payload: bytes = b"x" * 32) -> bytes:
    raw = bytes([0x80]) + struct.pack(">Q", when) + payload
    return base64.urlsafe_b64encode(raw) + b"\n"


def test_credentials_travel_only_when_carried_and_the_fresher_ciphertext_wins(
    tmp_path: Path,
) -> None:
    url = str(bare_remote(tmp_path))
    carried = SyncRemote(url=url, include_credentials=True)
    mac = Machine(tmp_path / "mac", "MacBook Pro", carried)
    mini = Machine(tmp_path / "mini", "Mac mini", carried)
    from coffer.application.sync.round_join import join

    mac.repo.set_carry_credentials(True)
    mac.put("credentials/provider/p1/key.enc", _fernet(1000))
    join(mac.engine, carried, None)
    join(mini.engine, carried, None)
    assert mini.disk("credentials/provider/p1/key.enc") == _fernet(1000)
    mac.put("credentials/provider/p1/key.enc", _fernet(2000))
    mini.put("credentials/provider/p1/key.enc", _fernet(1500))
    mac.round()
    # The mini's older ciphertext loses to the fresher one: nothing to push.
    assert mini.round().status is RoundStatus.PULLED
    assert mini.disk("credentials/provider/p1/key.enc") == _fernet(2000)


def test_ciphertext_never_leaves_a_machine_whose_remote_does_not_carry_it(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    mac.put("credentials/provider/p1/key.enc", _fernet(1000))
    mac.round()
    mini.round()
    assert mini.disk("credentials/provider/p1/key.enc") is None
    assert mac.repo.read("HEAD", "credentials/provider/p1/key.enc") is None


def test_a_remote_at_a_newer_layout_is_refused(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("manifest.json", '{\n  "schema_version": 4\n}\n')
    mac.round()
    head = mini.repo.head()
    assert mini.round().status is RoundStatus.REMOTE_TOO_NEW
    assert mini.repo.head() == head


def test_a_remote_at_an_older_layout_waits_for_its_upgrade(pair: tuple[Machine, Machine]) -> None:
    mac, mini = pair
    mac.put("manifest.json", '{\n  "schema_version": 2\n}\n')
    mac.round()
    assert mini.round().status is RoundStatus.WAITING_FOR_LAYOUT


def test_an_unreachable_remote_is_reported_and_nothing_changes(tmp_path: Path) -> None:
    gone = SyncRemote(url=str(tmp_path / "no-such-remote.git"))
    m = Machine(tmp_path / "m", "Mac", gone)
    m.state.set_joined(True)
    head = m.repo.head()
    got = m.round()
    assert got.status in (RoundStatus.UNREACHABLE, RoundStatus.AUTH_FAILED, RoundStatus.FAILED)
    assert m.repo.head() == head


@pytest.mark.parametrize(
    ("stderr", "problem"),
    [
        (
            "ssh: connect to host github.com port 22: Network is unreachable",
            RemoteProblem.UNREACHABLE,
        ),
        ("git@github.com: Permission denied (publickey).", RemoteProblem.AUTH_FAILED),
        (
            "! [remote rejected] main -> main (protected branch hook declined)",
            RemoteProblem.PUSH_REJECTED,
        ),
    ],
)
def test_remote_failures_are_classified_by_what_a_person_can_do(
    stderr: str, problem: RemoteProblem
) -> None:
    assert classify(stderr) is problem
