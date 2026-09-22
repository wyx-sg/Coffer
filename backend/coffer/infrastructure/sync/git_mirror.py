"""Drive one git working tree for vault convergence (spec vault-sync
``## The converge round``).

The adapter shells out to the real ``git`` binary rather than binding a library
because the point of the design is that what lands on the remote is an ordinary
git repository the user can clone, inspect and restore from with their own
tools — the same binary they would reach for.

This module is *what* the round asks git for. How an invocation is made safe —
the push credential's route through ``GIT_ASKPASS``, the user's own git config
pinned at ``/dev/null``, the redaction every raised message passes through —
is ``git_invoke.py`` beside it, because that changes for entirely different
reasons than a new git command does.

Nothing the user configured is ever the first thing after a subcommand. The
remote URL and the branch are validated in the domain (no leading ``-``), and
here every positional argument git lets us fence off sits behind ``--`` — a
``push`` is spelled as an explicit ``refs/heads/`` refspec because that command
takes no ``--``. The two layers are redundant on purpose.
"""

from __future__ import annotations

import pathlib
import re
from datetime import UTC, date, datetime

from coffer.infrastructure.sync.git_invoke import (
    DEFAULT_TIMEOUT_S,
    Completed,
    GitMirrorError,
    failure_message,
    run_git,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The all-zero object id ``git diff --raw`` prints for the side a change has
# none of: an addition has no "before", a deletion has no "after". It is not a
# content id and must never be compared as one.
_NULL_BLOB = re.compile(r"^0+$")

#: Written into the repository's *local* config the moment Coffer initialises
#: or adopts a working tree. Its absence on a repository whose ``origin`` is
#: somewhere else is how ``ensure_repo`` tells "the user's own checkout" from
#: "the tree Coffer made and the user has since repointed".
_MANAGED_KEY = "coffer.managed"


class GitMirror:
    """``GitMirrorPort`` over the ``git`` binary, rooted at one working tree."""

    EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def __init__(self, worktree: pathlib.Path, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._worktree = pathlib.Path(worktree)
        self._timeout = timeout_s

    @property
    def worktree(self) -> pathlib.Path:
        return self._worktree

    async def _git(self, *args: str, token: str | None = None, check: bool = True) -> Completed:
        """One git invocation in this working tree (see ``git_invoke``)."""
        return await run_git(
            self._worktree, *args, token=token, check=check, timeout_s=self._timeout
        )

    async def ensure_repo(self, *, remote_url: str, branch: str) -> None:
        """Make the working tree a repository on ``branch`` with ``origin`` set.

        An existing repository is adopted with its history rather than
        re-initialized: the user may have been pushing to this remote before
        Coffer was pointed at it, and a history discarded on the way in is
        not convergence. Adoption has one limit. A repository with commits
        whose ``origin`` already points somewhere *else*, and which Coffer did
        not create, is someone's checkout of something — the round would
        ``reset --hard`` it every hour — so it is refused rather than
        repointed. A tree Coffer made is marked as such and may be repointed
        freely, which is what changing the remote's URL does.
        """
        self._worktree.mkdir(parents=True, exist_ok=True)
        if not (self._worktree / ".git").exists():
            await self._git("init", "-b", branch)
        await self._set_origin(remote_url)
        await self._git("config", "--local", _MANAGED_KEY, "true")
        await self._ensure_branch(branch)

    async def _set_origin(self, remote_url: str) -> None:
        current = await self._git("remote", "get-url", "--", "origin", check=False)
        if current.returncode != 0:
            await self._git("remote", "add", "--", "origin", remote_url)
            return
        if current.stdout.strip() == remote_url:
            return
        managed = await self._git("config", "--local", "--get", _MANAGED_KEY, check=False)
        if managed.stdout.strip() != "true" and await self.head() is not None:
            raise GitMirrorError(
                f"{self._worktree} is already a repository with origin "
                f"{current.stdout.strip()}; it was not created by Coffer, so it is not "
                "adopted. Point the working tree at an empty directory instead."
            )
        await self._git("remote", "set-url", "--", "origin", remote_url)

    async def _ensure_branch(self, branch: str) -> None:
        if await self._current_branch() == branch:
            return
        if await self.head() is None:
            # Unborn HEAD: there is no commit to check out, so point the symbolic
            # ref at the wanted branch and let the first commit create it.
            await self._git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
            return
        # The trailing ``--`` makes the name a ref and never a path; with no
        # such branch this fails and one is created off the current commit.
        existing = await self._git("checkout", branch, "--", check=False)
        if existing.returncode != 0:
            await self._git("checkout", "-b", branch)

    async def _current_branch(self) -> str | None:
        out = await self._git("symbolic-ref", "--short", "HEAD", check=False)
        name = out.stdout.strip()
        return name if out.returncode == 0 and name else None

    async def stage_all(self) -> bool:
        """Stage everything; False when the export produced no difference.

        The caller uses this to decide whether to commit at all, so an
        unchanged vault leaves no empty commit in the history.
        """
        await self._git("add", "-A")
        diff = await self._git("diff", "--cached", "--quiet", check=False)
        if diff.returncode == 0:
            return False
        if diff.returncode == 1:
            return True
        raise GitMirrorError(failure_message(("diff",), diff, None))

    async def commit(self, message: str) -> str:
        await self._git("commit", "-m", message)
        out = await self._git("rev-parse", "--short", "HEAD")
        return out.stdout.strip()

    async def merge(self, ref: str, *, message: str) -> list[str]:
        """Merge ``ref`` into the current branch; return the conflicted paths.

        A conflict deliberately leaves the merge in progress: a resolver may yet
        write the files, and only the caller chooses between ``commit_merge`` and
        ``abort_merge``. Unrelated histories merge because a machine joining a
        remote it has never seen is that case, and the round wants the union."""
        done = await self._git(
            "merge", "--allow-unrelated-histories", "-m", message, ref, check=False
        )
        if done.returncode == 0:
            return []
        unmerged = await self._git("diff", "--name-only", "--diff-filter=U", "-z")
        conflicted = [path for path in unmerged.stdout.split("\0") if path]
        if not conflicted:
            raise GitMirrorError(failure_message(("merge",), done, None))
        return conflicted

    async def commit_merge(self, message: str) -> str:
        """Stage the resolved tree and conclude the merge git left in progress."""
        await self._git("add", "-A")
        return await self.commit(message)

    async def abort_merge(self) -> None:
        await self._git("merge", "--abort")

    async def take_side(self, path: str, side: str) -> None:
        """Resolve one conflicted path by taking ``ours`` or ``theirs`` — a git
        operation, not a file copy, so the index is left as the merge expects."""
        if side not in ("ours", "theirs"):
            raise GitMirrorError(f"not a merge side: {side}")
        await self._git("checkout", f"--{side}", "--", path)
        await self._git("add", "--", path)

    async def diff_paths(self, base: str, head: str) -> list[tuple[str, str, str]]:
        """``(status, path, blob)`` for every change between two commits.

        ``--no-renames`` so a move arrives as its delete and its add: the vault
        applies one path at a time. ``-z`` because a path may hold a newline.

        ``--raw`` rather than ``--name-status`` for one reason: it carries the
        content id of each side, which is what lets the deletion guard pair a
        deletion with the addition that received its bytes — a move — without
        reading a single file. ``--abbrev=40`` because raw output abbreviates
        by default, and a prefix is not an identity.

        The blob reported is the side the change is *about*: what a deletion
        removed, what an addition or a modification left behind. A line whose
        relevant side is all zeroes reports the empty string, which no caller
        may treat as content."""
        out = await self._git("diff", "--raw", "--abbrev=40", "--no-renames", "-z", base, head)
        fields = [field for field in out.stdout.split("\0") if field]
        changes = []
        for i in range(0, len(fields) - 1, 2):
            # ``:<old mode> <new mode> <old blob> <new blob> <status>``
            parts = fields[i].split(" ")
            if len(parts) < 5:  # pragma: no cover - git does not emit these
                continue
            status = parts[4][:1]
            blob = parts[2] if status == "D" else parts[3]
            changes.append((status, fields[i + 1], "" if _NULL_BLOB.match(blob) else blob))
        return changes

    async def renames(self, base: str, head: str) -> list[tuple[str, str]]:
        """``(source, destination)`` for the renames git detects between two
        commits — the guard's second way to show a deletion had a destination.

        A separate invocation from :meth:`diff_paths` on purpose. That one is
        rename-blind because the vault applies one path at a time, and it stays
        that way; this asks git the *other* question, and neither answer can
        disturb the other. The cost is one extra ``git diff`` per diff taken,
        over a tree of a few hundred small files.

        ``--diff-filter=R`` so every record is a rename and each is exactly
        three NUL-separated fields — metadata, source, destination — which is
        what makes this parse simpler than the raw one above rather than
        harder. ``-M`` at git's own default similarity: lowering it would
        excuse more deletions on less evidence, and there is nothing to base a
        different number on.

        Two ways this can legitimately return nothing, and both are safe by
        construction: git skips rename detection entirely once a diff exceeds
        ``diff.renameLimit``, and a relocation that rewrites a document past
        the similarity threshold is not paired. Either way the deletions simply
        count, and the round is held rather than waved through."""
        out = await self._git(
            "diff", "--raw", "--abbrev=40", "-M", "--diff-filter=R", "-z", base, head
        )
        fields = [field for field in out.stdout.split("\0") if field]
        # ``:<old mode> <new mode> <old blob> <new blob> R<score>\0<src>\0<dst>``
        return [
            (fields[i + 1], fields[i + 2])
            for i in range(0, len(fields) - 2, 3)
            if fields[i].startswith(":")
        ]

    async def file_count(self, revision: str, prefix: str) -> int:
        """Files a commit holds under ``prefix``, read from the tree so the share
        the deletion guard measures against cannot move mid-round."""
        scope = ["--", prefix] if prefix else []
        out = await self._git("ls-tree", "-r", "--name-only", "-z", revision, *scope)
        return sum(1 for path in out.stdout.split("\0") if path)

    async def reset_hard(self, revision: str) -> None:
        await self._git("reset", "--hard", revision)

    async def tag(self, name: str, revision: str) -> None:
        await self._git("tag", "-f", name, revision)

    async def tags(self, prefix: str) -> list[str]:
        out = await self._git("tag", "--list", f"{prefix}*", "--sort=-creatordate")
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]

    async def delete_tag(self, name: str) -> None:
        await self._git("tag", "-d", name)

    async def read_file(self, revision: str, path: str) -> bytes | None:
        """One file's bytes at a revision, or None when it is not there.

        ``revision`` may be a merge stage (``:2`` ours, ``:3`` theirs), which
        ``<revision>:<path>`` spells correctly on its own. Bytes rather than
        text: a credential blob is ciphertext a lossy decode would corrupt."""
        out = await self._git("show", f"{revision}:{path}", check=False)
        return out.stdout_bytes if out.returncode == 0 else None

    async def read_worktree(self, path: str) -> bytes | None:
        """What a resolver actually wrote — the validation gate's only input."""
        target = self._worktree / path
        return target.read_bytes() if target.is_file() else None

    async def push(self, *, branch: str, token: str | None) -> None:
        # ``push`` takes no ``--``; an explicit refspec is what keeps the
        # branch from ever being parsed as anything but a ref.
        refspec = f"refs/heads/{branch}:refs/heads/{branch}"
        await self._git("push", "origin", refspec, token=token)

    async def fetch(self, *, token: str | None) -> None:
        await self._git("fetch", "origin", token=token)

    async def resolve_revision(self, revision: str) -> str:
        """Full sha for a sha, a ref, or a ``YYYY-MM-DD`` date.

        A date resolves to the last commit at or before the *end* of that day,
        because "restore what I had on the 9th" means the state the 9th ended
        in, not the state it started with.
        """
        wanted = revision.strip()
        if not wanted:
            raise GitMirrorError("a revision is required")
        if wanted.startswith("-"):
            raise GitMirrorError(f"not a usable revision: {wanted}")
        if _DATE_RE.match(wanted):
            return await self._revision_at_date(wanted)
        return await self._verify(wanted)

    async def _verify(self, ref: str) -> str:
        found = await self._git(
            "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}", check=False
        )
        sha = found.stdout.strip()
        if found.returncode != 0 or not sha:
            raise GitMirrorError(f"unknown revision: {ref}")
        return sha

    async def _revision_at_date(self, day: str) -> str:
        try:
            cutoff = date.fromisoformat(day)
        except ValueError as exc:
            raise GitMirrorError(f"not a usable date: {day}") from exc
        start = await self._current_branch() or "HEAD"
        if cutoff >= datetime.now(tz=UTC).date():
            # git's own date parser cannot represent a far-future day at all
            # (it silently resolves to nothing), and a cutoff at or after today
            # means "the newest commit you have" anyway.
            return await self._verify(start)
        found = await self._git("rev-list", "-1", f"--before={day} 23:59:59", start)
        sha = found.stdout.strip()
        if not sha:
            raise GitMirrorError(f"no commit at or before {day}")
        return sha

    async def head(self) -> str | None:
        out = await self._git("rev-parse", "HEAD", check=False)
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else None
