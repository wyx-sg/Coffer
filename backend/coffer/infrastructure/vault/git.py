"""One ``git`` process over the vault repository.

Every invocation names the git directory and the work tree explicitly, so a
vault that has no repository yet can never be mistaken for a parent
directory's. Each runs with the user's global and system git configuration
pinned to ``/dev/null``, hooks switched off, and the commit identity given in
the environment: a developer's own git settings must not change what the
daemon records, and Coffer must not write an identity into any config.

A remote credential reaches git only through a **credential helper** on the
command line that reads it from an environment variable — never in the URL,
never in argv, never in ``.git/config`` — and every captured stderr is
redacted of it before it is raised (ADR credentials-across-machines).

Synchronous on purpose: local calls take milliseconds and every caller runs
them off the event loop (``asyncio.to_thread``) or inside a thread already;
a network call is the same call with a longer timeout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from coffer.domain.error_base import CofferError
from coffer.domain.vault.writers import author_name

LOCAL_TIMEOUT_S = 60.0
NETWORK_TIMEOUT_S = 120.0

_EMAIL = "coffer@localhost"
_TOKEN_ENV = "COFFER_GIT_TOKEN"
#: Answers ``get`` with the token from the environment; ignores ``store`` and
#: ``erase``, so nothing persists the secret. Safe in argv: it names the
#: variable, not its value.
_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get && printf "username=coffer\\npassword=%s\\n" "$COFFER_GIT_TOKEN"; }; f'
)
_PINNED = (
    "-c",
    "core.quotepath=false",
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.precomposeunicode=true",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "tag.gpgsign=false",
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "init.defaultBranch=main",
    "-c",
    "gc.auto=0",
)


class VaultGitError(CofferError):
    """A git invocation over the vault failed; the message is redacted."""

    code = "VAULT_GIT_FAILED"


class GitMissing(CofferError):  # noqa: N818
    """``git`` is not installed; the vault cannot keep its history."""

    code = "GIT_MISSING"

    def __init__(self) -> None:
        super().__init__(
            "git is not installed. Coffer keeps the vault's history with git; on macOS run "
            "`xcode-select --install`, then restart Coffer."
        )


def git_available() -> bool:
    return shutil.which("git") is not None


def redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


def _env(root: Path, writer: str | None, token: str | None) -> dict[str, str]:
    env = dict(os.environ)
    for leftover in (
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "SSH_ASKPASS_REQUIRE",
        _TOKEN_ENV,
        "GIT_INDEX_FILE",
    ):
        env.pop(leftover, None)
    env["GIT_DIR"] = str(root / ".git")
    env["GIT_WORK_TREE"] = str(root)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    name = author_name(writer)
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = name
        env[f"GIT_{role}_EMAIL"] = _EMAIL
    if token:
        env[_TOKEN_ENV] = token
    return env


def run(
    root: Path,
    *args: str,
    check: bool = True,
    stdin: bytes | None = None,
    writer: str | None = None,
    literal: bool = False,
    token: str | None = None,
    timeout: float = LOCAL_TIMEOUT_S,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """``git <args>`` over the repository at ``root``, output captured.

    ``literal`` turns pathspec magic off, so a path is always the path it
    names. ``token`` adds the credential helper for a remote call.
    """
    argv = ["git", *_PINNED]
    if token:
        argv += ["-c", "credential.helper=", "-c", f"credential.helper={_CREDENTIAL_HELPER}"]
    if literal:
        argv.append("--literal-pathspecs")
    argv += list(args)
    env = _env(root, writer, token)
    if extra_env:
        env.update(extra_env)
    try:
        done = subprocess.run(
            argv,
            cwd=root if root.is_dir() else None,
            env=env,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitMissing() from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultGitError(f"git {_subcommand(args)} timed out after {timeout:.0f}s") from exc
    if check and done.returncode != 0:
        raise VaultGitError(failure_message(args, done, token))
    return done


def failure_message(
    args: tuple[str, ...] | list[str],
    done: subprocess.CompletedProcess[bytes],
    token: str | None = None,
) -> str:
    detail = (
        done.stderr.decode("utf-8", "replace").strip()
        or done.stdout.decode("utf-8", "replace").strip()
        or f"exit {done.returncode}"
    )
    return redact(f"git {_subcommand(args)} failed: {detail}", token)


def _subcommand(args: tuple[str, ...] | list[str]) -> str:
    return next((a for a in args if not a.startswith("-")), "")


def text(done: subprocess.CompletedProcess[bytes]) -> str:
    return done.stdout.decode("utf-8", "replace")


__all__ = [
    "LOCAL_TIMEOUT_S",
    "NETWORK_TIMEOUT_S",
    "GitMissing",
    "VaultGitError",
    "failure_message",
    "git_available",
    "redact",
    "run",
    "text",
]
