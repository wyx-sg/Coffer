"""One thin sync round (spec vault-sync "Run a round as pull, merge, guard, check out, push").

::

    0 Check     — not inside a synchronised folder; the vault is a repository
    1 Local     — settle a person's valid edits; L := HEAD
    2 Fetch     — R := origin/<branch>
    3 Merge     — git merge-tree L R -> T, outside the working tree
    4 Stop?     — any conflict (content, identity, validation): stop, whole
    5 Guard     — the deletion breaker, incoming (L->T) and outgoing (base->L)
    6 Check out — snapshot L; M := commit(T; L, R); read-tree -m -u L M under
                  the vault's write lock, refusing if an edit is in the way
    7 Publish   — this machine's descriptor; refuse a plaintext secret; push

Nothing Coffer did on its own ever needs to be found and undone: a clean merge
is applied unattended, and everything else waits for the person with the vault
and the remote untouched.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from coffer.application.sync import round_plaintext
from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_guard import hold_for, invalid_files
from coffer.application.sync.round_layout import layout_refusal
from coffer.application.sync.round_trees import (
    conflict_files,
    identity_conflicts,
    settle_machines,
    settle_secrets,
)
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.domain.sync.stops import ConflictFile, HoldDirection, Stop, StopKind
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.remote_errors import RemoteFailed, RemoteProblem
from coffer.domain.vault.writers import OP_UPDATE, WRITER_DAEMON, CommitMeta
from coffer.domain.vault.writes import CommitResult, Expect

PROBLEM_STATUS = {
    RemoteProblem.UNREACHABLE: RoundStatus.UNREACHABLE,
    RemoteProblem.AUTH_FAILED: RoundStatus.AUTH_FAILED,
    RemoteProblem.PUSH_REJECTED: RoundStatus.PUSH_FAILED,
    RemoteProblem.OTHER: RoundStatus.FAILED,
}


class Recorder:
    """Builds a round's record with its start time and trigger filled in."""

    def __init__(self, deps: RoundDeps, started: str, trigger: str) -> None:
        self._deps = deps
        self._started = started
        self._trigger = trigger

    def __call__(self, status: RoundStatus, **fields: Any) -> RoundRecord:
        return RoundRecord(
            status=status,
            started_at=self._started,
            finished_at=self._deps.now(),
            trigger=self._trigger,
            **fields,
        )


class RoundEngine:
    """Runs rounds against one remote; one round at a time."""

    def __init__(self, deps: RoundDeps) -> None:
        self.d = deps

    # --- the round -------------------------------------------------------------

    def run(self, remote: SyncRemote, token: str | None, *, trigger: str = "timer") -> RoundRecord:
        with self.d.lock:
            return self._run(remote, token, trigger)

    def _run(self, remote: SyncRemote, token: str | None, trigger: str) -> RoundRecord:
        d = self.d
        started = d.now()
        rec = Recorder(d, started, trigger)
        where = d.cloud_folder()
        if where:
            return rec(RoundStatus.PAUSED_CLOUD_FOLDER, detail=where)
        d.git.ensure()
        d.git.set_remote(remote.url, remote.username)
        d.git.set_carry_secret(remote.include_secret)
        d.writer.settle()
        local = d.git.head()
        if local is None:
            return rec(RoundStatus.FAILED, detail="the vault has no commit yet")
        try:
            tip = d.git.fetch(remote.branch, token)
        except RemoteFailed as exc:
            return rec(PROBLEM_STATUS[exc.problem], detail=exc.detail)
        stop = d.state.stop()
        if stop is not None:
            if stop.local == local and stop.remote == tip:
                status = RoundStatus.HELD if stop.kind is StopKind.HOLD else RoundStatus.STOPPED
                return rec(
                    status,
                    conflicts=len(stop.unanswered),
                    held=len(stop.hold.paths) if stop.hold else 0,
                    from_commit=local,
                    to_commit=tip,
                )
            d.state.set_stop(None)  # a side moved since the question: ask it again
        if tip is None:
            if not d.state.joined():
                return rec(RoundStatus.JOIN_REQUIRED, detail="the remote is empty")
            return self._push(rec, remote, token, local, None)
        refused = layout_refusal(d, tip)
        if refused is not None:
            return rec(refused[0], detail=refused[1])
        base = d.git.merge_base(local, tip)
        if base is None:
            d.state.set_joined(False)
            return rec(
                RoundStatus.JOIN_REQUIRED, detail="this vault shares no history with the remote"
            )
        if not d.state.joined():
            # Shared history is not consent: a machine pointed at a new remote
            # (a mirror, a renamed repository, a clone) joins only when the
            # person previews and chooses to (spec vault-sync "Join a new
            # machine by taking the union").
            return rec(
                RoundStatus.JOIN_REQUIRED, detail="this machine has not joined this remote yet"
            )
        if local == tip:
            return rec(RoundStatus.NOTHING_TO_DO, from_commit=local, to_commit=local)
        if d.git.is_ancestor(tip, local):
            return self._push(rec, remote, token, local, tip)
        return self.converge(rec, remote, token, local, tip, base)

    def converge(
        self,
        rec: Recorder,
        remote: SyncRemote,
        token: str | None,
        local: str,
        tip: str,
        base: str | None,
        *,
        explicit_base: bool = False,
        join: str | None = None,
    ) -> RoundRecord:
        """Steps 3-7 for a local and a remote commit that have diverged (or a
        fast-forward). ``explicit_base`` merges against ``base`` rather than
        git's own merge base (a returning machine's join)."""
        d = self.d
        if not explicit_base and d.git.is_ancestor(local, tip):
            tree, entries = d.git.tree_of(tip), []
        else:
            merged = d.git.merge(local, tip, base=base if explicit_base else None)
            tree, entries = merged.tree, list(merged.conflicts)
        tree, entries = settle_secrets(d.git, tree, entries)
        tree = settle_machines(d.git, tree, tip, d.machine.descriptor_path(), base=base)
        found = conflict_files(entries) + identity_conflicts(d.trees, tree, local, tip)
        if not found:
            found = invalid_files(d.git, d.validate, d.history, local=local, merged=tree)
        if found:
            return self._stop(rec, local, tip, base, tree, found, join=join)
        return self.apply(rec, remote, token, local, tip, base, tree, join=join)

    def _stop(
        self,
        rec: Recorder,
        local: str,
        tip: str,
        base: str | None,
        tree: str,
        found: list[ConflictFile],
        *,
        join: str | None,
    ) -> RoundRecord:
        d = self.d
        labels = d.labels(tip)
        dated = [self._dated(c, local, tip, base, labels) for c in found]
        d.state.set_stop(
            Stop(
                StopKind.CONFLICTS,
                local,
                tip,
                base,
                d.now(),
                conflicts=tuple(dated),
                tree=tree,
                join=join,
            )
        )
        return rec(
            RoundStatus.STOPPED, conflicts=len(dated), from_commit=local, to_commit=tip, join=join
        )

    def _dated(
        self, c: ConflictFile, local: str, tip: str, base: str | None, labels: dict[str, str]
    ) -> ConflictFile:
        ours = self.d.git.log(c.path, start=local, limit=1)
        theirs = self.d.git.log(c.path, start=tip, limit=1)
        machine = theirs[0].meta.machine if theirs else None
        return dataclasses.replace(
            c,
            ours_time=ours[0].time.isoformat(timespec="seconds") if ours else None,
            theirs_time=theirs[0].time.isoformat(timespec="seconds") if theirs else None,
            theirs_machine=labels.get(machine or "", machine),
        )

    def apply(
        self,
        rec: Recorder,
        remote: SyncRemote,
        token: str | None,
        local: str,
        tip: str,
        base: str | None,
        tree: str,
        *,
        join: str | None = None,
    ) -> RoundRecord:
        """Steps 5-7 for a merged tree nothing stops on."""
        d = self.d
        confirmed = d.state.confirmed() == (local, tip)
        hold = hold_for(d.git, d.trees, before=local, after=tree, direction=HoldDirection.INCOMING)
        if hold is None and base is not None:
            hold = hold_for(
                d.git, d.trees, before=base, after=local, direction=HoldDirection.OUTGOING
            )
        if hold is not None and not confirmed:
            d.state.set_stop(
                Stop(StopKind.HOLD, local, tip, base, d.now(), hold=hold, tree=tree, join=join)
            )
            return rec(
                RoundStatus.HELD, held=len(hold.paths), from_commit=local, to_commit=tip, join=join
            )
        pulled, machines = d.pulled(local, tip)
        fast_forward = tree == d.git.tree_of(tip) and d.git.is_ancestor(local, tip)
        with d.writer.lock:
            if d.git.head() != local:
                return rec(
                    RoundStatus.WAITING_ON_EDIT,
                    detail="the vault changed during the round; the next round retries",
                )
            snapshot = d.git.snapshot(local)
            merged = (
                tip
                if fast_forward
                else d.git.commit_tree(tree, (local, tip), d.sync_meta(_summary(machines)))
            )
            try:
                d.git.checkout(local, merged)
            except VaultFileStale as exc:
                return rec(RoundStatus.WAITING_ON_EDIT, path=exc.path, detail=str(exc))
        applied = d.changes(local, merged)
        if applied:
            d.writer.notify(
                CommitResult(merged, d.sync_meta("Applied"), tuple(a.path for a in applied))
            )
        d.state.set_stop(None)
        d.state.set_confirmed(None)
        if d.scratch is not None:
            d.scratch.clear()
        final = self._publish_descriptor(merged)
        common: dict[str, Any] = {
            "from_commit": local,
            "to_commit": final,
            "snapshot": snapshot,
            "pulled": pulled,
            "applied": applied,
            "with_machines": machines,
            "join": join,
        }
        if final != tip:
            checked = round_plaintext.check(d, tip, final)
            if checked.findings or checked.moved:
                return round_plaintext.refused(rec, checked, **common)
            final = common["to_commit"] = self._after_fold(checked)
            common["folded"] = checked.folded
        pushed = d.changes(tip, final) if final != tip else ()
        if final != tip:
            try:
                d.git.push(final, remote.branch, token)
            except RemoteFailed as exc:
                return rec(RoundStatus.PUSH_FAILED, detail=exc.detail, **common)
        status = (
            RoundStatus.JOINED
            if join
            else RoundStatus.PULLED_AND_PUSHED
            if applied and pushed
            else RoundStatus.PULLED
            if applied
            else RoundStatus.PUSHED
            if pushed
            else RoundStatus.NOTHING_TO_DO
        )
        return rec(status, pushed=pushed, **common)

    def _push(
        self,
        rec: Recorder,
        remote: SyncRemote,
        token: str | None,
        local: str,
        tip: str | None,
    ) -> RoundRecord:
        """Nothing to pull: guard what this machine's commits delete, then push."""
        d = self.d
        confirmed = d.state.confirmed() == (local, tip or "")
        if tip is not None and not confirmed:
            hold = hold_for(
                d.git, d.trees, before=tip, after=local, direction=HoldDirection.OUTGOING
            )
            if hold is not None:
                d.state.set_stop(
                    Stop(
                        StopKind.HOLD,
                        local,
                        tip,
                        tip,
                        d.now(),
                        hold=hold,
                        tree=d.git.tree_of(local),
                    )
                )
                return rec(RoundStatus.HELD, held=len(hold.paths), from_commit=local, to_commit=tip)
        final = self._publish_descriptor(local)
        checked = round_plaintext.check(d, tip, final)
        if checked.findings or checked.moved:
            return round_plaintext.refused(rec, checked, from_commit=tip, to_commit=final)
        final = self._after_fold(checked)
        pushed = d.changes(tip, final)
        try:
            d.git.push(final, remote.branch, token)
        except RemoteFailed as exc:
            return rec(
                PROBLEM_STATUS[exc.problem],
                detail=exc.detail,
                from_commit=tip,
                to_commit=final,
                pushed=pushed,
                folded=checked.folded,
            )
        d.state.set_confirmed(None)
        return rec(
            RoundStatus.PUSHED,
            from_commit=tip,
            to_commit=final,
            pushed=pushed,
            folded=checked.folded,
        )

    def _after_fold(self, checked: round_plaintext.PushCheck) -> str:
        """The commit to push after a plaintext check. A fold makes a new commit
        the descriptor inside it knows nothing of (it names the commit that was
        folded away, which the remote never receives), so the descriptor is
        written again over the folded commit: what is pushed names a commit the
        remote holds, and a reinstall of this machine is recognised."""
        if not checked.folded:
            return checked.commit
        return self._publish_descriptor(checked.commit)

    def _publish_descriptor(self, commit: str) -> str:
        """Write this machine's descriptor when it changed; answer the commit
        to push (``commit`` itself when nothing changed)."""
        d = self.d
        path = d.machine.descriptor_path()
        data = d.machine.descriptor(last_round_at=d.now(), last_commit=commit)
        if d.git.read(commit, path) == data:
            return commit
        meta = CommitMeta(
            writer=WRITER_DAEMON, operation=OP_UPDATE, summary=f"Described {d.machine.label()}"
        )
        try:
            version = d.writer.write_file(path, data, meta=meta, expected=Expect.HEAD)
        except VaultFileStale:
            return commit
        return version or commit


def _summary(machines: tuple[str, ...]) -> str:
    return (
        f"Merged changes from {', '.join(machines)}"
        if machines
        else "Merged changes from the remote"
    )


__all__ = ["PROBLEM_STATUS", "Recorder", "RoundEngine"]
