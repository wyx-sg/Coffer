"""Drive one git working tree for vault convergence (spec vault-sync
``## The converge round``).

The adapter shells out to the real ``git`` binary rather than binding a library
because the point of the design is that what lands on the remote is an ordinary
git repository the user can clone, inspect and restore from with their own
tools — the same binary they would reach for.

The push credential is why the rest of this module is shaped the way it is. It
reaches git through ``GIT_ASKPASS`` plus an environment variable and nowhere
else: never interpolated into the remote URL, never in argv (which any process
on the machine can read), never written into ``.git/config`` (which is itself
pushed to a remote the user may share). The askpass script is a ``0o700`` temp
file deleted in a ``finally``, so a crash leaves no readable helper behind, and
every captured stderr passes through ``redact`` before it is raised — git
echoes the URL it tried back at you when authentication fails.

Each invocation also runs with ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM``
pointed at ``/dev/null`` and its commit identity supplied with ``-c``: a
developer's own git config must not be able to change what the daemon's round
does, and Coffer must not write an identity into the user's repository.

Nothing the user configured is ever the first thing after a subcommand. The
remote URL and the branch are validated in the domain (no leading ``-``), and
here every positional argument git lets us fence off sits behind ``--`` — a
``push`` is spelled as an explicit ``refs/heads/`` refspec because that command
takes no ``--``. The two layers are redundant on purpose.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import re
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import NamedTuple

from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import redact

DEFAULT_TIMEOUT_S = 120.0

# Reads the token from the environment and writes it to stdout: git asks this
# helper for the password instead of prompting, so the secret is never an
# argument and never touches the terminal.
_ASKPASS_BODY = "#!/bin/sh\nprintf '%s' \"$COFFER_GIT_TOKEN\"\n"
_TOKEN_ENV = "COFFER_GIT_TOKEN"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Pinned onto every invocation rather than passed per command, so nothing added
# later can be reached without them: quotepath keeps a path out of git's
# C-quoting — a note named in Chinese otherwise comes back escaped and matches
# no file on disk — and the identity is what a commit is authored as, the
# user's own git config being pinned at /dev/null below.
_QUOTEPATH = ("-c", "core.quotepath=false")
_IDENTITY = ("-c", "user.name=Coffer", "-c", "user.email=coffer@localhost")
_PINNED = _QUOTEPATH + _IDENTITY

#: Written into the repository's *local* config the moment Coffer initialises
#: or adopts a working tree. Its absence on a repository whose ``origin`` is
#: somewhere else is how ``ensure_repo`` tells "the user's own checkout" from
#: "the tree Coffer made and the user has since repointed".
_MANAGED_KEY = "coffer.managed"


class GitMirrorError(CofferError):
    """A git invocation failed; the message is already redacted. Maps to 502."""

    code = "GIT_MIRROR_FAILED"


class _Completed(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
    stdout_bytes: bytes = b""


@contextlib.contextmanager
def _askpass_script(token: str | None) -> Iterator[str | None]:
    """Yield the path to a private askpass helper, deleted on the way out.

    Without a token there is nothing to hand over and no file is created, so a
    local-path or already-authenticated remote costs nothing.
    """
    if not token:
        yield None
        return
    fd, path = tempfile.mkstemp(prefix="coffer-askpass-", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(_ASKPASS_BODY)
        os.chmod(path, 0o700)
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def _git_env(token: str | None, askpass: str | None) -> dict[str, str]:
    """The environment one git invocation runs in.

    Inherits the parent environment for ``PATH`` and friends, then pins
    everything that could change git's behaviour or leak the secret: any
    askpass helper the user already had is dropped, and the token is added only
    when this call actually needs it.
    """
    env = dict(os.environ)
    for leftover in ("GIT_ASKPASS", "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", _TOKEN_ENV):
        env.pop(leftover, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if token and askpass:
        env["GIT_ASKPASS"] = askpass
        env[_TOKEN_ENV] = token
    return env


class GitMirror:
    """``GitMirrorPort`` over the ``git`` binary, rooted at one working tree."""

    EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def __init__(self, worktree: pathlib.Path, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._worktree = pathlib.Path(worktree)
        self._timeout = timeout_s

    @property
    def worktree(self) -> pathlib.Path:
        return self._worktree

    async def _git(
        self,
        *args: str,
        token: str | None = None,
        check: bool = True,
    ) -> _Completed:
        """Run ``git -C <worktree> <args>`` and capture its output.

        ``asyncio.create_subprocess_exec`` — never a shell — so nothing in
        ``args`` can be re-parsed as a command, and a remote URL or branch name
        that happens to contain shell metacharacters is just a string.
        """
        with _askpass_script(token) as askpass:
            env = _git_env(token, askpass)
            argv = ("git", "-C", str(self._worktree), *_PINNED, *args)
            pipe = asyncio.subprocess.PIPE
            proc = await asyncio.create_subprocess_exec(*argv, stdout=pipe, stderr=pipe, env=env)
            try:
                raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise GitMirrorError(
                    f"git {args[0]} timed out after {self._timeout:.0f}s"
                ) from None
        text = raw_out.decode("utf-8", errors="replace")
        problem = raw_err.decode("utf-8", errors="replace")
        done = _Completed(proc.returncode or 0, text, problem, raw_out)
        if check and done.returncode != 0:
            raise GitMirrorError(self._failure(args, done, token))
        return done

    @staticmethod
    def _failure(args: tuple[str, ...], done: _Completed, token: str | None) -> str:
        detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}"
        subcommand = next((arg for arg in args if not arg.startswith("-")), "git")
        return redact(f"git {subcommand} failed: {detail}", token)

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
        raise GitMirrorError(self._failure(("diff",), diff, None))

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
            raise GitMirrorError(self._failure(("merge",), done, None))
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

    async def diff_paths(self, base: str, head: str) -> list[tuple[str, str]]:
        """``(status, path)`` for every change between two commits.

        ``--no-renames`` so a move arrives as its delete and its add: the vault
        applies one path at a time. ``-z`` because a path may hold a newline."""
        out = await self._git("diff", "--name-status", "--no-renames", "-z", base, head)
        fields = [field for field in out.stdout.split("\0") if field]
        return [(fields[i][:1], fields[i + 1]) for i in range(0, len(fields) - 1, 2)]

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
