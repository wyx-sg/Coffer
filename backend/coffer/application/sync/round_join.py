"""Joining a remote this vault has never converged with
(spec vault-sync "Report a join before applying it", "Join a new machine by
taking the union", "Recover a returning machine's base from its descriptor").

The preview and the join read the same facts, so what the person is shown is
what happens. A join never deletes a file on either side; a same-name
resource with a different uid stops the join and asks.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from coffer.application.sync import round_plaintext
from coffer.application.sync.round_engine import PROBLEM_STATUS, Recorder, RoundEngine
from coffer.application.sync.round_layout import layout_refusal
from coffer.application.sync.round_trees import identity_conflicts, settle_machines
from coffer.domain.sync.joins import AreaCount, JoinKind, JoinPreview
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import AppliedChange, RoundRecord, RoundStatus
from coffer.domain.sync.stops import ConflictFile, ConflictReason
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.layout import MACHINES, MANIFEST, area_of
from coffer.domain.vault.remote_errors import RemoteFailed
from coffer.domain.vault.writes import CommitResult


def _content(files: dict[str, str]) -> dict[str, str]:
    return {p: b for p, b in files.items() if not p.startswith(MACHINES + "/") and p != MANIFEST}


def _areas(paths: list[str]) -> tuple[AreaCount, ...]:
    counted = Counter(area_of(p) for p in paths)
    return tuple(AreaCount(a, n) for a, n in sorted(counted.items()))


def returning_base(engine: RoundEngine, tip: str) -> str | None:
    """The commit this machine last converged at, from its own descriptor in
    the remote — if that commit is still in the remote's history."""
    d = engine.d
    raw = d.git.read(tip, d.machine.descriptor_path())
    if raw is None:
        return None
    try:
        commit = json.loads(raw.decode("utf-8")).get("last_converged_commit")
    except (ValueError, AttributeError):
        return None
    if not isinstance(commit, str) or not commit:
        return None
    return commit if d.git.is_ancestor(commit, tip) else None


def preview(engine: RoundEngine, remote: SyncRemote, token: str | None) -> JoinPreview:
    d = engine.d
    d.git.ensure()
    d.git.set_remote(remote.url, remote.username)
    d.git.set_carry_secret(remote.include_secret)
    d.writer.settle()
    local = d.git.head() or ""
    tip = d.git.fetch(remote.branch, token)
    mine = _content(d.git.files(local))
    if tip is None:
        return JoinPreview(JoinKind.EMPTY, None, pushed=_areas(sorted(mine)))
    refused = layout_refusal(d, tip)
    if refused is not None:
        return JoinPreview(JoinKind.NEW, tip, refused=refused[1])
    newest = d.git.log(start=tip, limit=1)
    labels = d.labels(tip)
    pushed_by = labels.get(newest[0].meta.machine or "", newest[0].meta.machine) if newest else None
    pushed_at = newest[0].time.isoformat(timespec="seconds") if newest else None
    base = d.git.merge_base(local, tip) or returning_base(engine, tip)
    if base is not None:
        merged = d.git.merge(local, tip, base=base)
        tree = settle_machines(d.git, merged.tree, tip, d.machine.descriptor_path())
        here = [c for c in d.git.diff(local, tree) if not c.path.startswith(MACHINES + "/")]
        there = [c for c in d.git.diff(tip, tree) if not c.path.startswith(MACHINES + "/")]
        return JoinPreview(
            JoinKind.RETURNING,
            tip,
            pushed_by=pushed_by,
            pushed_at=pushed_at,
            pulled=_areas([c.path for c in here if c.status != "D"]),
            deleted=tuple(sorted({c.path for c in here + there if c.status == "D"})),
            conflicts=tuple(
                c.path for c in merged.conflicts if not c.path.startswith(MACHINES + "/")
            ),
            pushed=_areas([c.path for c in there]),
            base=base,
        )
    theirs = _content(d.git.files(tip))
    union = d.git.build_tree(d.git.tree_of(tip), {p: b for p, b in mine.items() if p not in theirs})
    clashes = identity_conflicts(d.trees, union, local, tip)
    return JoinPreview(
        JoinKind.NEW,
        tip,
        pushed_by=pushed_by,
        pushed_at=pushed_at,
        pulled=_areas(sorted(p for p in theirs if p not in mine)),
        same=sum(1 for p, b in mine.items() if theirs.get(p) == b),
        differ=tuple(sorted(p for p, b in mine.items() if p in theirs and theirs[p] != b)),
        pushed=_areas(sorted(p for p in mine if p not in theirs)),
        same_name=tuple(c.path for c in clashes),
    )


def join(engine: RoundEngine, remote: SyncRemote, token: str | None) -> RoundRecord:
    """Join as the preview said: push into an empty remote, merge against the
    recovered base, or take the union."""
    with engine.d.lock:
        d = engine.d
        rec = Recorder(d, d.now(), "manual")
        try:
            shown = preview(engine, remote, token)
        except RemoteFailed as exc:
            return rec(PROBLEM_STATUS[exc.problem], detail=exc.detail)
        local = d.git.head() or ""
        if shown.refused is not None and shown.remote_tip is not None:
            refused = layout_refusal(d, shown.remote_tip)
            if refused is not None:
                return rec(refused[0], detail=refused[1])
        d.state.set_joined(True)
        if shown.kind is JoinKind.EMPTY:
            return engine._push(rec, remote, token, local, None)
        tip = shown.remote_tip or ""
        if shown.kind is JoinKind.RETURNING:
            return engine.converge(
                rec,
                remote,
                token,
                local,
                tip,
                shown.base,
                explicit_base=True,
                join=JoinKind.RETURNING.value,
            )
        return _union(engine, rec, remote, token, local, tip, shown)


def _union(
    engine: RoundEngine,
    rec: Recorder,
    remote: SyncRemote,
    token: str | None,
    local: str,
    tip: str,
    shown: JoinPreview,
) -> RoundRecord:
    d = engine.d
    mine = _content(d.git.files(local))
    theirs = _content(d.git.files(tip))
    tree = d.git.build_tree(d.git.tree_of(tip), {p: b for p, b in mine.items() if p not in theirs})
    clashes = identity_conflicts(d.trees, tree, local, tip)
    if clashes:
        return engine._stop(rec, local, tip, None, tree, clashes, join=JoinKind.NEW.value)
    differ = list(shown.differ)
    kept = {p: d.writer.read_disk(p) for p in differ}
    with d.writer.lock:
        if d.git.head() != local:
            return rec(RoundStatus.WAITING_ON_EDIT, detail="the vault changed during the join")
        snapshot = d.git.snapshot(local)
        merged = d.git.commit_tree(tree, (local, tip), d.sync_meta("Joined the remote"))
        try:
            d.git.checkout(local, merged)
        except VaultFileStale as exc:
            return rec(RoundStatus.WAITING_ON_EDIT, path=exc.path, detail=str(exc))
        d.state.set_join_choices(
            [
                ConflictFile(
                    path=p,
                    area=area_of(p),
                    reason=ConflictReason.JOIN_DIFFERS,
                    ours=mine.get(p),
                    theirs=theirs.get(p),
                )
                for p in differ
            ]
        )
        for path, data in kept.items():
            if data is not None:
                d.writer.restore_disk(path, data)
    applied = tuple(AppliedChange(p, "added") for p in sorted(theirs) if p not in mine)
    if applied:
        d.writer.notify(CommitResult(merged, d.sync_meta("Joined"), tuple(a.path for a in applied)))
    final = engine._publish_descriptor(merged)
    pulled, machines = d.pulled(local, tip)
    common: dict[str, Any] = {
        "from_commit": local,
        "to_commit": final,
        "snapshot": snapshot,
        "pulled": pulled,
        "applied": applied,
        "with_machines": machines,
        "join": JoinKind.NEW.value,
        "held": len(differ),
    }
    checked = round_plaintext.check(d, tip, final)
    if checked.findings or checked.moved:
        return round_plaintext.refused(rec, checked, **common)
    final = common["to_commit"] = checked.commit
    common["folded"] = checked.folded
    pushed = d.changes(tip, final)
    try:
        d.git.push(final, remote.branch, token)
    except RemoteFailed as exc:
        return rec(RoundStatus.PUSH_FAILED, detail=exc.detail, **common)
    return rec(RoundStatus.JOINED, pushed=pushed, **common)


__all__ = ["join", "preview", "returning_base"]
