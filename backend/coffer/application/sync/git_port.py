"""The git working tree the vault converges through (spec vault-sync).

Split out of ``ports.py`` because it is half of that file on its own, and
because it is the only port here that reaches the network. It is re-exported
from ``ports`` so callers still have one import site.
"""

from __future__ import annotations

from typing import Protocol


class GitMirrorPort(Protocol):
    """The git working tree the vault converges through (spec vault-sync).

    git is the arbiter, not a transport: the three-way merge below is what
    decides whose edit survives and whether a missing document means "deleted"
    or "never had it". Everything the round does afterwards is reading the
    result of that merge as a diff.

    The only port in this slice that reaches the network, and the only place
    the push credential is ever materialised. Implementations must keep the
    token out of the repository's config, out of argv, and out of the text of
    any error they raise — it is handed over per call rather than held on the
    adapter so it lives no longer than the one git invocation that needs it.
    """

    #: git's constant hash of the empty tree. The base a machine joining a
    #: remote for the first time diffs against, which is what makes that
    #: round's diff additions-only by construction rather than by a check.
    EMPTY_TREE: str

    async def merge(self, ref: str, *, message: str) -> list[str]:
        """Merge ``ref`` into the current branch; return conflicted paths.

        An empty list means the merge committed cleanly (or was already up to
        date). A non-empty list leaves the merge **in progress** so a resolver
        can write the files and the caller can commit or abort — the caller
        decides, because a conflict an agent may still fix is not a failure
        yet."""

    async def commit_merge(self, message: str) -> str:
        """Stage the working tree and conclude an in-progress merge."""

    async def abort_merge(self) -> None:
        """Undo an in-progress merge, leaving the tree at the pre-merge commit."""

    async def diff_paths(self, base: str, head: str) -> list[tuple[str, str]]:
        """``(status, path)`` for every change between two commits.

        ``status`` is one of ``A`` / ``M`` / ``D``; a rename is reported as its
        delete and add, because the vault applies paths and has no use for the
        pairing. ``base`` may be ``EMPTY_TREE``."""

    async def file_count(self, revision: str, prefix: str) -> int:
        """How many files a revision holds under ``prefix``.

        The denominator the deletion guard measures a share against, read from
        the commit rather than the working tree so an in-flight round cannot
        move it."""

    async def reset_hard(self, revision: str) -> None:
        """Force the working tree and index to ``revision``.

        The round's repair step: a tree left somewhere unexpected by a crash is
        returned to the pointer before anything is serialized onto it."""

    async def tag(self, name: str, revision: str) -> None:
        """Create (or move) a lightweight tag — the pre-apply snapshot."""

    async def tags(self, prefix: str) -> list[str]:
        """Tags under ``prefix``, newest first, so old snapshots can be pruned."""

    async def delete_tag(self, name: str) -> None: ...

    async def read_file(self, revision: str, path: str) -> bytes | None:
        """One file's content at a revision, or None when it is not there.

        ``revision`` may be a merge stage — ``":2"`` for ours, ``":3"`` for
        theirs — which is how a conflicted file's two sides are read without
        parsing conflict markers out of the working copy."""

    async def read_worktree(self, path: str) -> bytes | None:
        """One file's content as it currently sits in the working tree.

        The only way to see what a resolver actually wrote, which is what the
        validation gate has to inspect before the round trusts it."""

    async def take_side(self, path: str, side: str) -> None:
        """Resolve one conflicted path by taking ``"ours"`` or ``"theirs"``.

        A git operation rather than a file copy, so the index is left in the
        state git expects for the rest of the merge."""

    async def ensure_repo(self, *, remote_url: str, branch: str) -> None:
        """Initialize the working tree, or adopt an existing repository there,
        and point ``origin`` at ``remote_url`` with ``branch`` checked out."""

    async def stage_all(self) -> bool:
        """Stage everything; True when the staged tree differs from ``HEAD``."""

    async def staged_paths(self) -> list[str]:
        """Repository-relative paths of what is staged, so a caller can tell a
        real change from one that only restamped the bundle's manifest."""

    async def discard_staged(self) -> None:
        """Return the working tree and index to ``HEAD``.

        Called when a staged diff turns out not to be worth committing: an
        index left dirty makes git refuse the next ``checkout``, which is the
        operation a restore-from-history depends on."""

    async def commit(self, message: str) -> str:
        """Commit what is staged and return the short sha."""

    async def push(self, *, branch: str, token: str | None) -> None:
        """Push ``branch`` to ``origin``; raises on failure, already redacted."""

    async def clone(self, *, remote_url: str, branch: str, token: str | None) -> None:
        """Clone the remote into the working tree (restore on a fresh machine)."""

    async def fetch(self, *, token: str | None) -> None: ...

    async def resolve_revision(self, revision: str) -> str:
        """Full sha for a sha, a ref, or a ``YYYY-MM-DD`` date (the last commit
        at or before it) — the three things a user can name a restore point by."""

    async def checkout(self, revision: str) -> None:
        """Detached checkout, so restoring from history never moves the branch."""

    async def checkout_branch(self, branch: str) -> None:
        """Return to the branch tip after a detached checkout."""

    async def head(self) -> str | None: ...

    async def has_unpushed(self, *, branch: str) -> bool:
        """True when local commits are ahead of ``origin/<branch>``; a run whose
        push failed leaves its commit behind for the next run to carry."""
