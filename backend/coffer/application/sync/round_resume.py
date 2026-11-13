"""Continuing a round that stopped for a person
(spec vault-sync "Answer each conflicting file and continue the round").

The stop is a question about one pair of commits. When the person has
answered every file, the resolved tree takes exactly the path a clean merge
takes: identity and validation checks again, the snapshot, the checkout, the
push. If either side moved while the
question was open, the round is re-derived and asked again.
"""

from __future__ import annotations

from coffer.application.sync.round_engine import PROBLEM_STATUS, Recorder, RoundEngine
from coffer.application.sync.round_guard import invalid_files
from coffer.application.sync.round_trees import identity_conflicts, overrides_for
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.domain.sync.stops import stop_fields
from coffer.domain.vault.remote_errors import RemoteFailed


def resume(
    engine: RoundEngine, remote: SyncRemote, token: str | None, *, trigger: str = "manual"
) -> RoundRecord:
    """Continue a stop once every file has an answer; re-derive it when either
    side moved."""
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
        if stop.unanswered:
            return rec(
                RoundStatus.STOPPED,
                **stop_fields(stop),
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


__all__ = ["resume"]
