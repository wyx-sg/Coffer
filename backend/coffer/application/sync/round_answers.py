"""A person's answers: to a stopped round's files, to a hold, to a join's
differing files (spec vault-sync "Answer each conflicting file and continue
the round", "Hold a round that would lose too much", "Join a new machine by
taking the union").

Answers are recorded, never applied one by one: nothing is written into the
vault until the round continues with every file answered. The editor answer
opens a marked-up copy under ``derived/sync-conflicts/`` — the vault's own
file never receives a conflict marker — and saving it back is refused while a
marker is left in it.

An agent may merge the files both machines edited: the hand-off is recorded
(:func:`hand_off`), the agent writes its merge into the same marked-up copy, and
the file is then shown as merged by an agent. It is an answer only once the
person marks it resolved — the ``edited`` answer, read from the copy — or goes
:func:`discard_copy` back to the two choices (spec vault-sync "Hand conflicting files to
an agent"). An encrypted secret is never hand-merged: it is answered
with one side or the other.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from coffer.application.sync.round_engine import RoundEngine
from coffer.application.sync.round_merge import (
    MERGED_BY_AGENT,
    marked_up,
    marker_line,
    merge_info,
)
from coffer.domain.error_base import CofferError
from coffer.domain.sync.handoffs import agent_mergeable, is_secret_file
from coffer.domain.sync.stops import (
    Answer,
    ConflictFile,
    Stop,
    StopKind,
    with_handoff,
    without_handoff,
)
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.writers import OP_UPDATE, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import CommitResult, Expect


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
        line = marker_line(data)
        if line is not None:
            raise SyncConflictMarkersLeft(path, line)
        edited = d.git.hash(data)
    try:
        updated = stop.with_answer(path, choice, edited)
    except KeyError:
        raise SyncNothingStopped(f"{path} is not one of the stopped round's files") from None
    d.state.set_stop(updated)
    return updated


def editor_copy(engine: RoundEngine, path: str, *, join: bool = False) -> str:
    """Write git's marked-up merge of ``path`` to the scratch area; answer
    where it is, for "Open in editor" and for an agent's hand-off. ``join``
    reads a join's differing files instead of the stopped round's."""
    d = engine.d
    found = _find(_open_files(engine, join), path)
    if found is None or d.scratch is None:
        raise SyncNothingStopped(f"{path} is not one of the stopped round's files")
    if is_secret_file(path):
        raise SyncSecretNotEditable(path)
    existing = d.scratch.where(path)
    if existing is not None:
        return existing
    return d.scratch.write(path, marked_up(d, found))


def hand_off(
    engine: RoundEngine,
    paths: Sequence[str] | None,
    *,
    join: bool,
    agent: str | None,
    conversation: str | None,
) -> tuple[str, ...]:
    """Record ``paths`` (every file an agent may merge when ``None``) as handed
    to an agent, writing each one's marked-up copy, and answer those paths. A
    file already merged is asked again from the marked-up text; one only handed
    over keeps its time and takes the agent or conversation now named."""
    d = engine.d
    open_files = _open_files(engine, join)
    by_path = {c.path: c for c in open_files}
    wanted = (
        [c.path for c in open_files if agent_mergeable(c) and c.answer is None]
        if paths is None
        else list(paths)
    )
    if not wanted:
        raise SyncNothingStopped("no file is waiting for an agent's merge")
    for path in wanted:
        found = by_path.get(path)
        if found is None:
            raise SyncNothingStopped(f"{path} is not one of the files waiting on you")
        if is_secret_file(path):
            raise SyncSecretNotEditable(path)
        if not agent_mergeable(found):
            raise SyncNothingStopped(f"{path} is a decision, not a merge an agent can make")
    for path in wanted:
        info = merge_info(d, by_path[path])
        if info is not None and info.state == MERGED_BY_AGENT:
            discard_copy(engine, path, join=join)
        editor_copy(engine, path, join=join)
    _store(
        engine,
        join,
        with_handoff(
            _open_files(engine, join),
            wanted,
            at=d.now(),
            agent=agent,
            conversation=conversation,
        ),
    )
    return tuple(wanted)


def discard_copy(engine: RoundEngine, path: str, *, join: bool) -> tuple[ConflictFile, ...]:
    """Back to two choices: forget the marked-up copy, the hand-off and any
    answer for ``path``, which is unresolved again. What the person or the
    agent wrote in the copy is gone."""
    d = engine.d
    open_files = _open_files(engine, join)
    if _find(open_files, path) is None:
        raise SyncNothingStopped(f"{path} is not one of the files waiting on you")
    if d.scratch is not None:
        d.scratch.discard(path)
    return _store(engine, join, without_handoff(open_files, path))


def _open_files(engine: RoundEngine, join: bool) -> tuple[ConflictFile, ...]:
    state = engine.d.state
    if join:
        return state.join_choices()
    stop = state.stop()
    return stop.conflicts if stop is not None and stop.kind is StopKind.CONFLICTS else ()


def _store(
    engine: RoundEngine, join: bool, files: tuple[ConflictFile, ...]
) -> tuple[ConflictFile, ...]:
    state = engine.d.state
    if join:
        state.set_join_choices(files)
        return files
    stop = state.stop()
    assert stop is not None  # _open_files found files only because a stop exists
    state.set_stop(dataclasses.replace(stop, conflicts=files))
    return files


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
                # A held file's bytes on disk are deliberately not HEAD's, so
                # the expectation is the held bytes themselves: restoring
                # replaces exactly what the person was shown, nothing newer.
                held = d.writer.read_disk(path)
                txn.write(path, data, fingerprint(held) if held is not None else Expect.ABSENT)
    d.state.set_stop(None)
    return txn.version


def choose_join(
    engine: RoundEngine, path: str, choice: Answer, *, actor: str
) -> tuple[ConflictFile, ...]:
    """Settle one of a join's differing files: keep this machine's version
    (committed now, pushed by the next round), take the other's (written here,
    nothing to commit), or take the merge in its marked-up copy (committed
    now, like keeping this machine's)."""
    d = engine.d
    choices = list(d.state.join_choices())
    found = _find(choices, path)
    if found is None:
        raise SyncNothingStopped(f"{path} is not waiting for a join choice")
    merged: bytes | None = None
    if choice is Answer.EDITED:
        if is_secret_file(path):
            raise SyncSecretNotEditable(path)
        merged = d.scratch.read(path) if d.scratch else None
        if merged is None:
            raise SyncNothingStopped(f"open {path} in the editor first")
        line = marker_line(merged)
        if line is not None:
            raise SyncConflictMarkersLeft(path, line)
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
    if merged is not None:
        meta = CommitMeta(
            writer=WRITER_USER,
            operation=OP_UPDATE,
            summary=f"Merged {path} from both machines",
            actor=actor,
        )
        with d.writer.begin(meta) as txn:
            held = d.writer.read_disk(path)
            txn.write(path, merged, fingerprint(held) if held is not None else Expect.ABSENT)
        if d.scratch is not None:
            d.scratch.discard(path)
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
    "discard_copy",
    "editor_copy",
    "hand_off",
    "restore_held",
]
