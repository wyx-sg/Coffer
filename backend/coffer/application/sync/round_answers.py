"""A person's answers: to a stopped round's files, to a hold, to a join's
differing files (spec vault-sync "Answer each conflicting file and continue
the round", "Hold a round that would lose too much", "Join a new machine by
taking the union").

Answers are recorded, never applied one by one: nothing is written into the
vault until the round continues with every file answered. The editor answer
opens a marked-up copy under ``derived/sync-conflicts/`` — the vault's own
file never receives a conflict marker — and saving it back is refused while a
marker is left in it.

An agent may merge the files both machines edited: it edits the same
marked-up copies, and the person records every copy it merged at once with
**I merged it** (:func:`mark_merged`, spec vault-sync "Hand a conflict's merge
to an agent"). An encrypted secret is never hand-merged: it is answered with
one side or the other.
"""

from __future__ import annotations

import re

from coffer.application.sync.round_engine import RoundEngine
from coffer.domain.error_base import CofferError
from coffer.domain.sync.handoffs import agent_mergeable, is_secret_file
from coffer.domain.sync.stops import Answer, ConflictFile, Stop, StopKind
from coffer.domain.vault.writers import OP_UPDATE, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import CommitResult

_MARKER = re.compile(rb"^(<{7}|={7}|>{7})( |$)", re.M)


class SyncNothingStopped(CofferError):  # noqa: N818
    """No round is waiting for this answer. Maps to 409."""

    code = "SYNC_NOTHING_STOPPED"


class SyncConflictMarkersLeft(CofferError):  # noqa: N818
    """The hand-merged file still has conflict markers. Maps to 422."""

    code = "SYNC_CONFLICT_MARKERS_LEFT"

    def __init__(self, path: str, line: int) -> None:
        self.path = path
        self.line = line
        super().__init__(
            f"Line {line} of {path} still has conflict markers. "
            "Remove them, save, then mark it resolved."
        )


class SyncSecretNotEditable(CofferError):  # noqa: N818
    """An encrypted secret has no hand-merged version: keep one side. Maps to 422."""

    code = "SYNC_SECRET_NOT_EDITABLE"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"{path} is an encrypted secret: keep this machine's version or take the other's"
        )


def _marker_line(data: bytes) -> int | None:
    match = _MARKER.search(data)
    return data[: match.start()].count(b"\n") + 1 if match else None


def answer(engine: RoundEngine, path: str, choice: Answer) -> Stop:
    """Record ``choice`` for ``path`` in the stopped round. For ``edited``,
    the person's saved copy is read and checked for markers now."""
    d = engine.d
    stop = d.state.stop()
    if stop is None or stop.kind is not StopKind.CONFLICTS:
        raise SyncNothingStopped("no round is stopped on conflicts")
    edited: str | None = None
    if choice is Answer.EDITED:
        if is_secret_file(path):
            raise SyncSecretNotEditable(path)
        data = d.scratch.read(path) if d.scratch else None
        if data is None:
            raise SyncNothingStopped(f"open {path} in the editor first")
        line = _marker_line(data)
        if line is not None:
            raise SyncConflictMarkersLeft(path, line)
        edited = d.git.hash(data)
    try:
        updated = stop.with_answer(path, choice, edited)
    except KeyError:
        raise SyncNothingStopped(f"{path} is not one of the stopped round's files") from None
    d.state.set_stop(updated)
    return updated


def editor_copy(engine: RoundEngine, path: str) -> str:
    """Write git's marked-up merge of ``path`` to the scratch area; answer
    where it is, for "Open in editor"."""
    d = engine.d
    stop = d.state.stop()
    found = _find(stop.conflicts if stop else (), path)
    if stop is None or found is None or d.scratch is None:
        raise SyncNothingStopped(f"{path} is not one of the stopped round's files")
    if is_secret_file(path):
        raise SyncSecretNotEditable(path)
    existing = d.scratch.read(path)
    if existing is not None:
        return d.scratch.write(path, existing)
    blobs = d.git.blobs([b for b in (found.ours, found.base, found.theirs) if b])
    ours = blobs.get(found.ours or "", b"")
    base = blobs.get(found.base or "", b"")
    theirs = blobs.get(found.theirs or "", b"")
    marked = d.git.merge_file(
        ours, base, theirs, (d.machine.label(), found.theirs_machine or "the other machine")
    )
    return d.scratch.write(path, marked)


def mark_merged(engine: RoundEngine) -> Stop:
    """ "I merged it": record ``edited`` for every unanswered file an agent may
    merge, from its marked-up copy. Every copy is checked before any answer is
    recorded, so a copy with a marker left refuses the whole request."""
    d = engine.d
    stop = d.state.stop()
    if stop is None or stop.kind is not StopKind.CONFLICTS:
        raise SyncNothingStopped("no round is stopped on conflicts")
    handed = [c for c in stop.unanswered if agent_mergeable(c)]
    if not handed:
        raise SyncNothingStopped("no file of the stopped round is waiting for an agent's merge")
    blobs: dict[str, str] = {}
    for c in handed:
        data = d.scratch.read(c.path) if d.scratch else None
        if data is None:
            raise SyncNothingStopped(f"{c.path} has no marked-up copy to merge yet")
        line = _marker_line(data)
        if line is not None:
            raise SyncConflictMarkersLeft(c.path, line)
        blobs[c.path] = d.git.hash(data)
    updated = stop
    for path, blob in blobs.items():
        updated = updated.with_answer(path, Answer.EDITED, blob)
    d.state.set_stop(updated)
    return updated


def confirm_hold(engine: RoundEngine) -> Stop:
    """ "Apply the deletions": the next continue checks the held round out."""
    d = engine.d
    stop = d.state.stop()
    if stop is None or stop.kind is not StopKind.HOLD:
        raise SyncNothingStopped("no round is held")
    d.state.set_confirmed((stop.local, stop.remote))
    return stop


def restore_held(engine: RoundEngine, *, actor: str) -> str | None:
    """ "Restore them": keep the files the held round would remove. Incoming,
    the round's tree takes this machine's versions of them; outgoing, the
    deleted files are written back from the base as a person's commit, so the
    next round pushes them."""
    d = engine.d
    stop = d.state.stop()
    if stop is None or stop.kind is not StopKind.HOLD or stop.hold is None:
        raise SyncNothingStopped("no round is held")
    source = stop.local if stop.hold.direction.value == "incoming" else (stop.base or stop.remote)
    if stop.hold.direction.value == "incoming":
        keep = {p: d.git.files(source, p).get(p) for p in stop.hold.paths}
        tree = d.git.build_tree(stop.tree or d.git.tree_of(stop.remote), keep)
        d.state.set_stop(
            Stop(
                stop.kind,
                stop.local,
                stop.remote,
                stop.base,
                stop.raised_at,
                hold=stop.hold,
                tree=tree,
                join=stop.join,
            )
        )
        d.state.set_confirmed((stop.local, stop.remote))
        return None
    meta = CommitMeta(
        writer=WRITER_USER,
        operation="restore",
        summary=f"Restored {len(stop.hold.paths)} held files",
        actor=actor,
    )
    with d.writer.begin(meta) as txn:
        for path in stop.hold.paths:
            data = d.git.read(source, path)
            if data is not None:
                txn.write(path, data, None)
    d.state.set_stop(None)
    return txn.version


def choose_join(
    engine: RoundEngine, path: str, choice: Answer, *, actor: str
) -> tuple[ConflictFile, ...]:
    """Settle one of a join's differing files: keep this machine's version
    (committed now, pushed by the next round) or take the other's (written
    here, nothing to commit)."""
    d = engine.d
    choices = list(d.state.join_choices())
    found = _find(choices, path)
    if found is None:
        raise SyncNothingStopped(f"{path} is not waiting for a join choice")
    remaining = [c for c in choices if c.path != path]
    d.state.set_join_choices(remaining)
    head = d.git.head() or ""
    if choice is Answer.THEIRS:
        d.writer.restore_disk(path, d.git.read(head, path))
        d.writer.notify(
            CommitResult(
                head,
                CommitMeta(
                    writer=WRITER_USER, operation=OP_UPDATE, summary="Took the other version"
                ),
                (path,),
            )
        )
        return tuple(remaining)
    meta = CommitMeta(
        writer=WRITER_USER, operation=OP_UPDATE, summary=f"Kept this machine's {path}", actor=actor
    )
    with d.writer.begin(meta) as txn:
        txn.touch(path)
    return tuple(remaining)


def _find(
    conflicts: tuple[ConflictFile, ...] | list[ConflictFile], path: str
) -> ConflictFile | None:
    return next((c for c in conflicts if c.path == path), None)


__all__ = [
    "SyncConflictMarkersLeft",
    "SyncNothingStopped",
    "SyncSecretNotEditable",
    "answer",
    "choose_join",
    "confirm_hold",
    "editor_copy",
    "mark_merged",
    "restore_held",
]
