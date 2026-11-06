"""The breaker sets aside deletions Coffer can explain, and remembers a
confirmed hold by file (spec vault-sync "Count losses, not deletions",
"Ask the user to confirm a tripped breaker")."""

from __future__ import annotations

import pytest

from coffer.application.sync.round_answers import confirm_hold
from coffer.domain.knowledge.history import OP_TIDY
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.vault.writers import WRITER_AGENT, WRITER_MEMORY_SYNC, CommitMeta
from coffer.domain.vault.writes import Expect

from .machines import USER, Machine, remote_ref

MEMORY_SYNC = CommitMeta(
    writer=WRITER_MEMORY_SYNC, operation="memory-sync", summary="Memory sync: 25 removed"
)
TIDY = CommitMeta(writer=WRITER_AGENT, operation=OP_TIDY, summary="Tidied", agent="codex")


def _write(m: Machine, paths: list[str]) -> None:
    with m.writer.begin(USER) as txn:
        for p in paths:
            txn.write(p, f"{p}\n".encode(), Expect.ABSENT)


def _delete(m: Machine, meta: CommitMeta, paths: list[str]) -> None:
    with m.writer.begin(meta) as txn:
        for p in paths:
            txn.delete(p, Expect.HEAD)


def _memories(n: int, start: int = 0) -> list[str]:
    return [f"memory/global/m-{i}.md" for i in range(start, start + n)]


def _docs(n: int) -> list[str]:
    return [f"knowledge/team/doc-{i}.md" for i in range(n)]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a deletion Coffer can explain is not asked about"
)
def test_memory_sync_and_tidy_deletions_push_without_a_hold(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    _write(mac, _memories(30) + _docs(25))
    mac.round()
    mini.round()
    _delete(mac, MEMORY_SYNC, _memories(25))
    _delete(mac, TIDY, _docs(25))
    got = mac.round()
    assert got.status is RoundStatus.PUSHED, got
    # The other machine takes them in without a hold either.
    assert mini.round().status in (RoundStatus.PULLED, RoundStatus.PULLED_AND_PUSHED)
    assert mini.disk(_docs(1)[0]) is None
    assert mini.disk(_memories(1)[0]) is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a deletion Coffer can explain is not asked about"
)
def test_an_explained_deletion_that_empties_its_area_is_still_held(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    _write(mac, _memories(25))
    mac.round()
    mini.round()
    _delete(mac, MEMORY_SYNC, _memories(25))
    tip = remote_ref(mac.remote)
    got = mac.round()
    assert got.status is RoundStatus.HELD and got.held == 25
    assert remote_ref(mac.remote) == tip


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a hand deletion beside Coffer's own is still held"
)
def test_a_hand_deletion_beside_an_explained_one_is_held_alone(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    _write(mac, _memories(30) + _docs(25))
    mac.round()
    mini.round()
    _delete(mac, MEMORY_SYNC, _memories(25))
    mac.remove(*_docs(25))
    got = mac.round()
    assert got.status is RoundStatus.HELD and got.held == 25
    stop = mac.state.stop()
    assert stop and stop.hold and set(stop.hold.paths) == set(_docs(25))


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a confirmed hold is not asked again after a later edit"
)
def test_a_confirmed_hold_is_not_asked_again_after_a_later_edit(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    _write(mac, _docs(25))
    mac.round()
    mini.round()
    mac.remove(*_docs(25))
    assert mac.round().status is RoundStatus.HELD
    confirm_hold(mac.engine)
    # Something moves this vault before the round is continued — in the field,
    # a plaintext stop and its fix.
    mac.put("knowledge/team/after.md", "written after the hold was answered\n")
    got = mac.round()
    assert got.status is RoundStatus.PUSHED, got
