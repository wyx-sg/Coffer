"""The two ways a round runs backwards (spec vault-sync).

A **rollback** undoes an apply that should not have happened; a **rebuild**
gives up on this vault's own contents and takes the remote's. They share the
same shape — move the tree, apply the difference, put the tree back — and they
are here rather than in ``convergence.py`` because the forward round is already
a file's worth of algorithm on its own.

What both get right, and what is easy to get wrong: the working tree moves
**before** the apply, because every applier reads the document it is applying
out of the tree. Applying while the tree still stood where it was would rewrite
each changed file with the very content the move is undoing — a no-op dressed
as a restore.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus
from coffer.domain.sync.diff import ChangeStatus, DiffSummary

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.git_port import GitMirrorPort


class BackwardsMixin:
    """Rollback and rebuild, mixed into ``ConvergeRound``.

    The four members below are what this half borrows from the forward round.
    Declaring them is what lets this file be type-checked on its own rather
    than on the assumption that whatever it is mixed into happens to provide
    them.
    """

    _mirror: GitMirrorPort

    async def _diff(self, base: str, head: str) -> DiffSummary:
        raise NotImplementedError  # pragma: no cover - provided by ConvergeRound

    async def _serialize_and_commit(self, pointer: str) -> str:
        raise NotImplementedError  # pragma: no cover - provided by ConvergeRound

    async def apply(self, diff: DiffSummary) -> list[tuple[str, str]]:
        raise NotImplementedError  # pragma: no cover - provided by ConvergeRound

    async def reverse_to(self, current: str, target: str, *, delete: bool = True) -> ConvergeRun:
        """Return the vault to an earlier commit, and leave it publishable.

        The diff is applied with the working tree moved to ``target`` first,
        because every applier reads the document it is applying out of the
        tree; applying while the tree still stood at ``current`` would rewrite
        each changed file with the very content the move is undoing.

        The tree and the pointer are then **put back where they were**. That is
        the part that makes an undo stick. Moving the pointer back to
        ``target`` would make the next round's diff ``target..current`` — the
        same diff again — and the worker would silently re-apply on its next
        tick, which is exactly the outcome the operator reached for rollback to
        prevent. Left at ``current``, the reverted vault is an ordinary local
        change: the next round serializes it, publishes it, and the other
        machines receive the undo rather than re-imposing the work.

        ``delete=False`` separates a **restore** from a rollback. A rollback
        undoes a round whole, deletions included. A restore reaches back for
        something that was lost, and everything the vault gained since is not
        part of the question (spec vault-sync ``## Restore``).
        """
        started = datetime.now(tz=UTC)
        diff = await self._diff(current, target)
        if not delete:
            diff = DiffSummary.of([c for c in diff.changes if c.status is not ChangeStatus.DELETED])
        await self._mirror.reset_hard(target)
        try:
            failures = await self.apply(diff)
        finally:
            # Whatever happened to the vault, the tree goes back: leaving it at
            # ``target`` would make the next round read a base this vault no
            # longer matches.
            await self._mirror.reset_hard(current)
        return ConvergeRun(
            status=ConvergeStatus.OK,
            started_at=started,
            finished_at=datetime.now(tz=UTC),
            applied=diff,
            # The revision this went back to, not where the pointer ended up.
            # The pointer deliberately does not move, so reporting it would
            # tell the user only what they already knew; what they asked is
            # "from where?", and this answers it.
            commit=target,
            failures=tuple(failures),
        )

    async def rebuild_to(self, tip: str) -> ConvergeRun:
        """Make this vault equal the remote, discarding what only it holds.

        The honest answer for a machine whose vault is gone. Such a machine
        rejoins with a valid recovered base and an empty (or gutted) vault, and
        neither ordinary answer serves it: confirming publishes the loss to
        every other machine, and rejecting leaves it stuck refusing the same
        round forever.

        It works by serializing the vault onto the tree first, so the diff that
        follows can see what this machine has that the remote does not — those
        are the documents being discarded, and they have to exist as a commit
        before git can name them. The commit is then abandoned by the move to
        ``tip``; nothing is pushed, because a rebuild is this machine deciding
        to stop asserting anything.
        """
        # The tree's own HEAD is the fallback, not ``tip``: a vault that
        # serializes to no change must still be diffed from where it actually
        # stands. Passing ``tip`` there would make the diff empty and the
        # rebuild a silent no-op — which is exactly what a damaged machine
        # would then keep doing.
        here = await self._mirror.head() or tip
        local = await self._serialize_and_commit(here)
        return await self.reverse_to(local, tip)

    # --- held rounds --------------------------------------------------------
