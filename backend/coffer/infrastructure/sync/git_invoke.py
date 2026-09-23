"""How one ``git`` process is started, and how the push credential reaches it.

Extracted from ``git_mirror.py`` beside it, the way ``convergence_ops.py`` sits
beside ``convergence.py``, and along a real seam: that module is about *what*
the round asks git for — merge, diff, tag, push — while this one is about
making any such invocation safe. The two change for different reasons. A new
git command is added there; the rules below change only when the way a secret
or a user's own configuration could reach git changes.

The credential is why this module is shaped the way it is. It reaches git
through a **credential helper** given on the command line, which reads the
secret from an environment variable: never interpolated into the remote URL,
never in argv (which any process on the machine can read — the helper names
the variable, not its value), never written into ``.git/config`` (which is
itself pushed to a remote the user may share). Every captured stderr passes
through ``redact`` before it is raised, since git echoes the URL it tried back
at you when authentication fails. The token is handed over per call rather
than held on an adapter, so it lives no longer than the one invocation that
needs it.

It used to be handed over through ``GIT_ASKPASS``, which is a prompt path
rather than a credential path — and **macOS's own git does not take it**.
Apple's build answers ``fatal: unable to get password from user`` without ever
running the helper, so on the platform Coffer ships a desktop app for, the
token never reached git at all. What had been carrying authentication was the
``credential.helper = osxkeychain`` line in Xcode's system gitconfig, which
the ``GIT_CONFIG_NOSYSTEM`` below deliberately switches off — leaving sync
with no credential source whatsoever, and an hourly failure that says only
that nobody answered a prompt. A helper is not a prompt: it is asked first,
by every git, before any of that.

Each invocation also runs with ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM``
pointed at ``/dev/null`` and its commit identity supplied with ``-c``: a
developer's own git config must not be able to change what the daemon's round
does, and Coffer must not write an identity into the user's repository.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import NamedTuple

from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import redact

DEFAULT_TIMEOUT_S = 120.0

_TOKEN_ENV = "COFFER_GIT_TOKEN"

#: The credential helper git is given for an authenticated remote.
#:
#: A shell snippet (git runs a ``!``-prefixed helper through ``sh``) that
#: answers the ``get`` action with the token from the environment and ignores
#: ``store`` and ``erase`` — nothing here should persist a secret anywhere.
#: The value is read from ``$COFFER_GIT_TOKEN`` at helper runtime, so this
#: string is safe to sit in argv where every process on the machine can read
#: it.
#:
#: The username is a placeholder: a forge that authenticates with a token
#: ignores it (GitHub's own documentation uses one), and a real account name
#: here would only be a second thing to keep correct.
_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get && printf "username=coffer\npassword=%s\n" "$COFFER_GIT_TOKEN"; }; f'
)

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


def credential_args(token: str | None) -> tuple[str, ...]:
    """The ``-c`` flags that let git authenticate, or nothing without a token.

    Two settings, and the empty one first: assigning ``credential.helper`` an
    empty value clears every helper inherited from anywhere else before ours
    is appended, so a helper a user configured cannot answer ahead of it or
    quietly record the token.
    """
    if not token:
        return ()
    return ("-c", "credential.helper=", "-c", f"credential.helper={_CREDENTIAL_HELPER}")


def _git_env(token: str | None) -> dict[str, str]:
    """The environment one git invocation runs in.

    Inherits the parent environment for ``PATH`` and friends, then pins
    everything that could change git's behaviour or leak the secret: any
    prompt helper the user already had is dropped, and the token is added only
    when this call actually needs it.
    """
    env = dict(os.environ)
    for leftover in ("GIT_ASKPASS", "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", _TOKEN_ENV):
        env.pop(leftover, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if token:
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
    env = _git_env(token)
    argv = ("git", "-C", str(worktree), *_PINNED, *credential_args(token), *args)
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
