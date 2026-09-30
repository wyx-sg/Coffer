"""Continuing a round that stopped for a person
(spec vault-sync "Answer each conflicting file and continue the round").

The stop is a question about one pair of commits. When the person has
answered every file — or confirmed a hold — the resolved tree takes exactly
the path a clean merge takes: identity and validation checks again, the
breaker, the snapshot, the checkout, the push. If either side moved while the
question was open, the round is re-derived and asked again.
"""

from __future__ import annotations

from coffer.application.sync.round_engine import PROBLEM_STATUS, Recorder, RoundEngine
from coffer.application.sync.round_guard import invalid_files
from coffer.application.sync.round_trees import identity_conflicts, overrides_for
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.domain.sync.stops import HoldDirection, Stop, StopKind
from coffer.domain.vault.remote_errors import RemoteFailed


def resume(
    engine: RoundEngine, remote: SyncRemote, token: str | None, *, trigger: str = "manual"
) -> RoundRecord:
    """Continue a stop once every file has an answer (or a hold was
    confirmed); re-derive it when either side moved."""
    with engine.d.lock:
        d = engine.d
        started = d.now()
        rec = Recorder(d, started, trigger)
        stop = d.state.stop()
        if stop is None:
            return engine._run(remote, token, trigger)
        try:
            tip = d.git.fetch(remote.branch, token)
        except RemoteFailed as exc:
            return rec(PROBLEM_STATUS[exc.problem], detail=exc.detail)
        if d.git.head() != stop.local or tip != stop.remote:
            d.state.set_stop(None)
            return engine._run(remote, token, trigger)
        if stop.kind is StopKind.HOLD:
            return _resume_hold(engine, rec, remote, token, stop)
        if stop.unanswered:
            return rec(
                RoundStatus.STOPPED,
                conflicts=len(stop.unanswered),
                from_commit=stop.local,
                to_commit=stop.remote,
            )
        tree = d.git.build_tree(
            stop.tree or d.git.tree_of(stop.remote), overrides_for(stop.conflicts)
        )
        again = identity_conflicts(d.trees, tree, stop.local, stop.remote) + invalid_files(
            d.git, d.validate, d.history, local=stop.local, merged=tree
        )
        if again:
            return engine._stop(
                rec, stop.local, stop.remote, stop.base, tree, again, join=stop.join
            )
        d.state.set_stop(None)
        return engine.apply(
            rec, remote, token, stop.local, stop.remote, stop.base, tree, join=stop.join
        )


def _resume_hold(
    engine: RoundEngine, rec: Recorder, remote: SyncRemote, token: str | None, stop: Stop
) -> RoundRecord:
    d = engine.d
    if d.state.confirmed() != (stop.local, stop.remote):
        return rec(RoundStatus.HELD, held=len(stop.hold.paths) if stop.hold else 0)
    d.state.set_stop(None)
    if (
        stop.hold is not None
        and stop.hold.direction is HoldDirection.OUTGOING
        and stop.base == stop.remote
    ):
        return engine._push(rec, remote, token, stop.local, stop.remote)
    return engine.apply(
        rec,
        remote,
        token,
        stop.local,
        stop.remote,
        stop.base,
        stop.tree or d.git.tree_of(stop.remote),
        join=stop.join,
    )


__all__ = ["resume"]
