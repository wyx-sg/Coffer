"""Replacing a remote that holds an older layout
(spec vault-sync
"Refuse a newer-layout remote and replace an older one").

The upgraded vault is the source of truth. The push is a fast-forward: one
commit whose tree is exactly this machine's content, with this machine's
commit and the old remote tip as parents, so the old history stays in git.
The files only the old remote had go away on purpose, so the outgoing
deletion breaker does not apply; the plaintext check still does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coffer.application.sync import round_plaintext
from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.joins import AreaCount, JoinKind, JoinPreview
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import PROBLEM_STATUS, RoundRecord, RoundStatus
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.layout import MACHINES, MANIFEST, area_of
from coffer.domain.vault.remote_errors import RemoteFailed

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import Recorder, RoundEngine

#: How many removed paths a preview lists (the count is always exact).
DELETED_LISTED = 100

JOIN = JoinKind.REPLACE.value


def _content(files: dict[str, str]) -> dict[str, str]:
    return {p: b for p, b in files.items() if not p.startswith(MACHINES + "/") and p != MANIFEST}


def replace_preview(d: RoundDeps, tip: str, mine: dict[str, str]) -> JoinPreview:
    """What replacing the remote at ``tip`` with this vault would do."""
    theirs = _content(d.git.files(tip))
    counted: dict[str, int] = {}
    for p in mine:
        counted[area_of(p)] = counted.get(area_of(p), 0) + 1
    gone = sorted(p for p in theirs if p not in mine)
    newest = d.git.log(start=tip, limit=1)
    return JoinPreview(
        JoinKind.REPLACE,
        tip,
        # The old remote's machine descriptors are in the older layout's
        # format: never parsed here, so the machine is named by its id.
        pushed_by=newest[0].meta.machine if newest else None,
        pushed_at=newest[0].time.isoformat(timespec="seconds") if newest else None,
        pushed=tuple(AreaCount(a, n) for a, n in sorted(counted.items())),
        deleted=tuple(gone[:DELETED_LISTED]),
        deleted_total=len(gone),
    )


def replace(
    engine: RoundEngine,
    rec: Recorder,
    remote: SyncRemote,
    token: str | None,
    local: str,
    tip: str,
) -> RoundRecord:
    """Push this vault over the older-layout remote and mark the machine joined."""
    d = engine.d
    with d.writer.lock:
        if d.git.head() != local:
            return rec(RoundStatus.WAITING_ON_EDIT, detail="the vault changed during the round")
        merged = local
        if not d.git.is_ancestor(tip, local):
            merged = d.git.commit_tree(
                d.git.tree_of(local),
                (local, tip),
                d.sync_meta("Replaced the older-layout remote"),
            )
            try:
                d.git.checkout(local, merged)
            except VaultFileStale as exc:
                return rec(RoundStatus.WAITING_ON_EDIT, path=exc.path, detail=str(exc))
    d.state.set_joined(True)
    d.state.set_stop(None)
    final = engine._publish_descriptor(merged)
    checked = round_plaintext.check(d, tip, final)
    fields: dict[str, Any] = {"from_commit": tip, "join": JOIN}
    if checked.findings or checked.moved:
        return round_plaintext.refused(rec, checked, to_commit=final, **fields)
    final = engine._after_fold(checked)
    pushed = d.changes(tip, final)
    try:
        d.git.push(final, remote.branch, token)
    except RemoteFailed as exc:
        return rec(
            PROBLEM_STATUS[exc.problem],
            detail=exc.detail,
            to_commit=final,
            pushed=pushed,
            folded=checked.folded,
            **fields,
        )
    d.state.set_confirmed(None)
    return rec(RoundStatus.PUSHED, to_commit=final, pushed=pushed, folded=checked.folded, **fields)


__all__ = ["replace", "replace_preview"]
