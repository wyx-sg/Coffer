"""How one ``git`` process is started, and how the push credential reaches it.

Extracted from ``git_mirror.py`` beside it, the way ``convergence_ops.py`` sits
beside ``convergence.py``, and along a real seam: that module is about *what*
the round asks git for — merge, diff, tag, push — while this one is about
making any such invocation safe. The two change for different reasons. A new
git command is added there; the rules below change only when the way a secret
or a user's own configuration could reach git changes.

The push credential is why this module is shaped the way it is. It reaches git
through ``GIT_ASKPASS`` plus an environment variable and nowhere else: never
interpolated into the remote URL, never in argv (which any process on the
machine can read), never written into ``.git/config`` (which is itself pushed
to a remote the user may share). The askpass script is a ``0o700`` temp file
deleted in a ``finally``, so a crash leaves no readable helper behind, and
every captured stderr passes through ``redact`` before it is raised — git
echoes the URL it tried back at you when authentication fails. The token is
handed over per call rather than held on an adapter, so it lives no longer than
the one invocation that needs it.

Each invocation also runs with ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM``
pointed at ``/dev/null`` and its commit identity supplied with ``-c``: a
developer's own git config must not be able to change what the daemon's round
does, and Coffer must not write an identity into the user's repository.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import redact

DEFAULT_TIMEOUT_S = 120.0

# Reads the token from the environment and writes it to stdout: git asks this
# helper for the password instead of prompting, so the secret is never an
# argument and never touches the terminal.
_ASKPASS_BODY = "#!/bin/sh\nprintf '%s' \"$COFFER_GIT_TOKEN\"\n"
_TOKEN_ENV = "COFFER_GIT_TOKEN"

# Pinned onto every invocation rather than passed per command, so nothing added
# later can be reached without them: quotepath keeps a path out of git's
# C-quoting — a note named in Chinese otherwise comes back escaped and matches
# no file on disk — and the identity is what a commit is authored as, the
# user's own git config being pinned at /dev/null below.
_QUOTEPATH = ("-c", "core.quotepath=false")
_IDENTITY = ("-c", "user.name=Coffer", "-c", "user.email=coffer@localhost")
_PINNED = _QUOTEPATH + _IDENTITY


class GitMirrorError(CofferError):
    """A git invocation failed; the message is already redacted. Maps to 502."""

    code = "GIT_MIRROR_FAILED"


class Completed(NamedTuple):
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


def failure_message(args: tuple[str, ...], done: Completed, token: str | None) -> str:
    """What a failed invocation says, redacted.

    Public because a caller sometimes runs git with ``check=False`` to read an
    exit code it understands — ``diff --quiet`` answers in 0 or 1 — and has to
    raise for itself when the code is neither.
    """
    detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}"
    subcommand = next((arg for arg in args if not arg.startswith("-")), "git")
    return redact(f"git {subcommand} failed: {detail}", token)


async def run_git(
    worktree: Path,
    *args: str,
    token: str | None = None,
    check: bool = True,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Completed:
    """Run ``git -C <worktree> <args>`` and capture its output.

    ``asyncio.create_subprocess_exec`` — never a shell — so nothing in ``args``
    can be re-parsed as a command, and a remote URL or branch name that happens
    to contain shell metacharacters is just a string.
    """
    with _askpass_script(token) as askpass:
        env = _git_env(token, askpass)
        argv = ("git", "-C", str(worktree), *_PINNED, *args)
        pipe = asyncio.subprocess.PIPE
        proc = await asyncio.create_subprocess_exec(*argv, stdout=pipe, stderr=pipe, env=env)
        try:
            raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise GitMirrorError(f"git {args[0]} timed out after {timeout_s:.0f}s") from None
    text = raw_out.decode("utf-8", errors="replace")
    problem = raw_err.decode("utf-8", errors="replace")
    done = Completed(proc.returncode or 0, text, problem, raw_out)
    if check and done.returncode != 0:
        raise GitMirrorError(failure_message(args, done, token))
    return done
