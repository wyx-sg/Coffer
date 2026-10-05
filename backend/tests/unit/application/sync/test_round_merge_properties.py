"""Properties of a round's merge decision (ADR
sync-applies-clean-merges-and-stops-on-any-conflict; spec vault-sync "Run a
round as pull, merge, guard, check out, push", "Hold a round that would lose
too much").

A generated vault forks at a base; this machine and the remote each keep,
edit, delete or add files (or do nothing). One round runs over an in-memory
git (``fake_git``), and the decision is checked against an oracle:

- any path both sides changed differently stops the round, naming exactly
  those paths, with nothing snapshotted, checked out or pushed;
- a clean merge that loses more than the breaker allows, in either direction,
  is held, again with nothing checked out or pushed;
- any other clean merge is applied: the vault holds the merged files, the
  remote holds the vault's head, and the next round has nothing to do.

A stopped or held round asked again with neither side moved stops again,
still touching nothing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from hypothesis import event, given
from hypothesis import strategies as st

from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_engine import RoundEngine
from coffer.domain.sync.breaker import FLOOR, SHARE_MIN
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import HoldDirection, StopKind
from coffer.domain.vault.layout import MACHINES, area_of

from .fake_git import FakeGit, FakeMachine, FakeState, FakeWriter

_REMOTE = SyncRemote(url="https://example.invalid/vault.git")
_AREAS = ("knowledge", "skills")

Files = dict[str, bytes]


@dataclass(frozen=True)
class Fork:
    base: Files
    local: Files | None  # None: this machine made no commit since the base
    remote: Files | None  # None: the remote has not moved since the base


def _side(draw: st.DrawFn, base: Files, who: str) -> Files | None:
    if not draw(st.sampled_from((True, True, True, False)), label=f"{who} moved"):
        return None
    out: Files = {}
    # How destructive this side is, so both "a few files" and "most of an
    # area" are drawn often enough to reach both sides of the breaker.
    delete_weight = draw(st.sampled_from((0, 1, 3, 8)), label=f"{who} delete weight")
    edit_weight = draw(st.sampled_from((0, 1, 2)), label=f"{who} edit weight")
    fates = ("keep",) * 12 + ("edit", "shared-edit") * edit_weight + ("delete",) * delete_weight
    for path, data in base.items():
        fate = draw(st.sampled_from(fates), label=f"{who} {path}")
        if fate == "keep":
            out[path] = data
        elif fate == "edit":
            out[path] = f"{path} edited on {who}\n".encode()
        elif fate == "shared-edit":
            out[path] = f"{path} edited the same way on both\n".encode()
    for i in range(draw(st.integers(0, 4), label=f"{who} adds")):
        area = draw(st.sampled_from(_AREAS))
        shared = draw(st.booleans())
        path = f"{area}/new/{'shared' if shared else who}-{i}.md"
        out[path] = f"{path} added {'on both' if shared else 'on ' + who}\n".encode()
    return out


@st.composite
def forks(draw: st.DrawFn) -> Fork:
    base: Files = {}
    for area in _AREAS:
        for i in range(draw(st.integers(0, 30), label=f"{area} size")):
            path = f"{area}/d{i % 3}/f{i}.md"
            base[path] = f"{path} as it was\n".encode()  # unique bytes: nothing pairs as a move
    return Fork(base, _side(draw, base, "local"), _side(draw, base, "remote"))


# --- the oracle ------------------------------------------------------------------


def _merge(fork: Fork) -> tuple[Files, list[str]]:
    base = fork.base
    mine = fork.local if fork.local is not None else base
    theirs = fork.remote if fork.remote is not None else base
    merged: Files = {}
    conflicts: list[str] = []
    for path in sorted(set(base) | set(mine) | set(theirs)):
        b, m, t = base.get(path), mine.get(path), theirs.get(path)
        if m == t or t == b:
            pick = m
        elif m == b:
            pick = t
        else:
            conflicts.append(path)
            continue
        if pick is not None:
            merged[path] = pick
    return merged, conflicts


def _lost_too_much(before: Files, after: Files) -> list[str] | None:
    """The deleted paths when ``before -> after`` breaches an area, else None
    (the breaker's rule in integers; no bytes move, so every deletion is lost)."""
    gone = sorted(p for p in before if p not in after)
    held = Counter(area_of(p) for p in before)
    for area, lost in Counter(area_of(p) for p in gone).items():
        if lost >= FLOOR or (lost >= SHARE_MIN and 2 * lost > held[area]):
            return gone
    return None


def _content(files: Files) -> Files:
    return {p: d for p, d in files.items() if not p.startswith(MACHINES + "/")}


# --- the round -------------------------------------------------------------------


@dataclass
class Rig:
    git: FakeGit
    state: FakeState
    engine: RoundEngine
    local: str
    tip: str


def _rig(fork: Fork) -> Rig:
    git = FakeGit()
    base = git.commit(fork.base)
    local = git.commit(fork.local, (base,)) if fork.local is not None else base
    tip = git.commit(fork.remote, (base,)) if fork.remote is not None else base
    git.local, git.remote = local, tip
    state = FakeState()
    deps = RoundDeps(git=git, state=state, writer=FakeWriter(git), machine=FakeMachine())  # type: ignore[arg-type]
    return Rig(git, state, RoundEngine(deps), local, tip)


def _untouched(rig: Rig) -> None:
    assert rig.git.snapshotted == []
    assert rig.git.checkouts == []
    assert rig.git.pushes == []
    assert (rig.git.local, rig.git.remote) == (rig.local, rig.tip)


@given(forks())
def test_a_round_applies_a_clean_merge_and_stops_on_any_conflict(fork: Fork) -> None:
    rig = _rig(fork)
    got = rig.engine.run(_REMOTE, None)
    event(got.status.value)  # `--hypothesis-show-statistics` shows each outcome's share
    merged, conflicts = _merge(fork)
    local_files = fork.local if fork.local is not None else fork.base

    if fork.local is None and fork.remote is None:
        assert got.status is RoundStatus.NOTHING_TO_DO
        _untouched(rig)
        return

    if conflicts:
        assert got.status is RoundStatus.STOPPED
        stop = rig.state.current
        assert stop is not None and stop.kind is StopKind.CONFLICTS
        assert sorted(c.path for c in stop.conflicts) == conflicts
        assert (stop.local, stop.remote) == (rig.local, rig.tip)
        assert got.conflicts == len(conflicts)
        _untouched(rig)
        return

    incoming = _lost_too_much(local_files, merged) if fork.remote is not None else None
    outgoing = _lost_too_much(fork.base, local_files) if fork.local is not None else None
    if incoming is not None or outgoing is not None:
        assert got.status is RoundStatus.HELD
        stop = rig.state.current
        assert stop is not None and stop.kind is StopKind.HOLD and stop.hold is not None
        direction = HoldDirection.INCOMING if incoming is not None else HoldDirection.OUTGOING
        assert stop.hold.direction is direction
        assert list(stop.hold.paths) == (incoming if incoming is not None else outgoing)
        _untouched(rig)
        return

    # Both sides may have made the same changes: then nothing moves either way.
    assert got.status in (
        RoundStatus.PULLED,
        RoundStatus.PUSHED,
        RoundStatus.PULLED_AND_PUSHED,
        RoundStatus.NOTHING_TO_DO,
    )
    assert rig.state.current is None
    head = rig.git.local
    assert head is not None and rig.git.remote == head
    assert _content(rig.git.contents(head)) == merged
    assert rig.git.contents(head)[f"{MACHINES}/mac.json"]  # this machine described itself
    if fork.remote is None:  # nothing to pull: pushed as it stood, never checked out
        assert rig.git.checkouts == []
        assert _content(rig.git.contents(head)) == local_files
    else:
        assert rig.git.snapshotted == [rig.local]
        ((old, new),) = rig.git.checkouts
        assert old == rig.local
        assert _content(rig.git.contents(new)) == merged
        if fork.local is None:  # a fast-forward takes the remote's commit itself
            assert new == rig.tip
    again = rig.engine.run(_REMOTE, None)
    assert again.status is RoundStatus.NOTHING_TO_DO
    assert rig.git.remote == head and len(rig.git.pushes) == 1


@given(forks())
def test_a_stopped_or_held_round_asked_again_stops_again_and_touches_nothing(
    fork: Fork,
) -> None:
    rig = _rig(fork)
    first = rig.engine.run(_REMOTE, None)
    if first.status not in (RoundStatus.STOPPED, RoundStatus.HELD):
        return
    second = rig.engine.run(_REMOTE, None)
    assert second.status is first.status
    assert (second.conflicts, second.held) == (first.conflicts, first.held)
    _untouched(rig)
