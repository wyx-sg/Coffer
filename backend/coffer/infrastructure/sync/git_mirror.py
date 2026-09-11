"""Drive one git working tree for the vault backup (spec vault-export-import ``## Backup``).

The adapter shells out to the real ``git`` binary rather than binding a library
because the point of the backup is that what lands on the remote is an ordinary
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
developer's own git config must not be able to change what the daemon's backup
does, and Coffer must not write an identity into the user's repository.
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


class GitMirrorError(CofferError):
    """A git invocation failed; the message is already redacted. Maps to 502."""

    code = "GIT_MIRROR_FAILED"


class _Completed(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


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
        root: pathlib.Path | None = None,
    ) -> _Completed:
        """Run ``git -C <root> <args>`` and capture its output.

        ``asyncio.create_subprocess_exec`` — never a shell — so nothing in
        ``args`` can be re-parsed as a command, and a remote URL or branch name
        that happens to contain shell metacharacters is just a string.
        """
        cwd = root or self._worktree
        with _askpass_script(token) as askpass:
            env = _git_env(token, askpass)
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(cwd),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise GitMirrorError(
                    f"git {args[0]} timed out after {self._timeout:.0f}s"
                ) from None
        done = _Completed(
            proc.returncode or 0,
            raw_out.decode("utf-8", errors="replace"),
            raw_err.decode("utf-8", errors="replace"),
        )
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
        Coffer was pointed at it, and a backup that begins by discarding
        history is not a backup.
        """
        self._worktree.mkdir(parents=True, exist_ok=True)
        if not (self._worktree / ".git").exists():
            await self._git("init", "-b", branch)
        await self._set_origin(remote_url)
        await self._ensure_branch(branch)

    async def _set_origin(self, remote_url: str) -> None:
        current = await self._git("remote", "get-url", "origin", check=False)
        if current.returncode != 0:
            await self._git("remote", "add", "origin", remote_url)
        elif current.stdout.strip() != remote_url:
            await self._git("remote", "set-url", "origin", remote_url)

    async def _ensure_branch(self, branch: str) -> None:
        if await self._current_branch() == branch:
            return
        if await self.head() is None:
            # Unborn HEAD: there is no commit to check out, so point the symbolic
            # ref at the wanted branch and let the first commit create it.
            await self._git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
            return
        existing = await self._git("checkout", branch, check=False)
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
        await self._git(
            "-c",
            "user.name=Coffer",
            "-c",
            "user.email=coffer@localhost",
            "commit",
            "-m",
            message,
        )
        out = await self._git("rev-parse", "--short", "HEAD")
        return out.stdout.strip()

    async def push(self, *, branch: str, token: str | None) -> None:
        await self._git("push", "origin", branch, token=token)

    async def clone(self, *, remote_url: str, branch: str, token: str | None) -> None:
        parent = self._worktree.parent
        parent.mkdir(parents=True, exist_ok=True)
        await self._git("clone", remote_url, str(self._worktree), token=token, root=parent)
        await self.checkout_branch(branch)

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
        if _DATE_RE.match(wanted):
            return await self._revision_at_date(wanted)
        return await self._verify(wanted)

    async def _verify(self, ref: str) -> str:
        found = await self._git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
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
            # means "the newest backup you have" anyway.
            return await self._verify(start)
        found = await self._git("rev-list", "-1", f"--before={day} 23:59:59", start)
        sha = found.stdout.strip()
        if not sha:
            raise GitMirrorError(f"no backup commit at or before {day}")
        return sha

    async def checkout(self, revision: str) -> None:
        """Detached checkout, so reading an old revision never moves the branch."""
        await self._git("checkout", "--detach", revision)

    async def checkout_branch(self, branch: str) -> None:
        local = await self._git("checkout", branch, check=False)
        if local.returncode == 0:
            return
        await self._git("checkout", "-B", branch, f"origin/{branch}")

    async def head(self) -> str | None:
        out = await self._git("rev-parse", "HEAD", check=False)
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else None

    async def has_unpushed(self, *, branch: str) -> bool:
        """True when the branch is ahead of ``origin/<branch>``.

        A run whose push failed keeps its commit, so the next run must be able
        to see there is something to carry without re-exporting. A missing
        upstream is not an error: nothing was ever pushed, so every commit that
        exists is unpushed.
        """
        ahead = await self._git("rev-list", "--count", f"origin/{branch}..{branch}", check=False)
        if ahead.returncode == 0:
            return int(ahead.stdout.strip() or "0") > 0
        return await self.head() is not None
