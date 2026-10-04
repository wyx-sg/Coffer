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
redacted of it before it is raised (ADR secrets-cross-machines-only-as-ciphertext).

Synchronous on purpose: local calls take milliseconds and every caller runs
them off the event loop (``asyncio.to_thread``) or inside a thread already;
a network call is the same call with a longer timeout.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from coffer.domain.error_base import CofferError
from coffer.domain.git_handoff import VAULT_NEEDS_GIT_FOR, git_missing_details
from coffer.domain.vault.writers import author_name
from coffer.infrastructure.platform.host import machine_label

LOCAL_TIMEOUT_S = 60.0
NETWORK_TIMEOUT_S = 120.0

_EMAIL = "coffer@localhost"
_TOKEN_ENV = "COFFER_GIT_TOKEN"
#: Answers ``get`` with the token from the environment; ignores ``store`` and
#: ``erase``, so nothing persists the secret. Safe in argv: it names the
#: variable, not its value.
_USERNAME_ENV = "COFFER_GIT_USERNAME"
#: The username a token is paired with when the remote names none. GitHub and
#: GitLab ignore it for a token (GitLab: any non-blank value); Bitbucket and
#: Azure DevOps need a real one, which the remote settings carry.
DEFAULT_USERNAME = "coffer"
#: The remote's own origin, which the helper compares with what git asks about:
#: a redirect to another host is never handed the credential (spec secret
#: "Send a secret only to the origin it was approved for").
_PROTOCOL_ENV = "COFFER_GIT_PROTOCOL"
_HOST_ENV = "COFFER_GIT_HOST"
_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get || return 0; p=; h=; '
    'while IFS== read -r k v; do case "$k" in protocol) p=$v;; host) h=$v;; esac; done; '
    'test -n "$COFFER_GIT_HOST" && test "$p" = "$COFFER_GIT_PROTOCOL" '
    '&& test "$h" = "$COFFER_GIT_HOST" '
    '&& printf "username=%s\\npassword=%s\\n" "$COFFER_GIT_USERNAME" "$COFFER_GIT_TOKEN"; }; f'
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
            "git is not installed. Coffer keeps the vault's history and syncs it with git; "
            "install git, then restart Coffer."
        )
        # How git is installed depends on the machine, so the error names no
        # installer: its details carry the install hand-off for the person's
        # agent (``domain/git_handoff.py``), which the web UI offers and the
        # CLI prints.
        self.error_details = git_missing_details(machine_label(), needed_for=VAULT_NEEDS_GIT_FOR)


def git_available() -> bool:
    return shutil.which("git") is not None


@functools.lru_cache(maxsize=8)
def _executable(search_path: str | None) -> str:
    """The ``git`` binary itself, found once per ``PATH``.

    The ``git`` on ``PATH`` can be a launcher rather than git: the one Apple
    puts in ``/usr/bin`` looks up the developer tools on every call, which
    costs about 0.5 s a call on a busy machine (up to 1.7 s measured) against
    0.05 s for the binary it starts. A sync round makes hundreds of calls, so
    that lookup, not git, set how long a round took under load. Every git
    install keeps its own binary in its exec path, so ask once and call that.
    Falls back to plain ``git`` when the answer is not usable, and keyed by
    ``PATH`` so a changed ``PATH`` is looked up again.
    """
    try:
        done = subprocess.run(
            ["git", "--exec-path"],
            capture_output=True,
            timeout=LOCAL_TIMEOUT_S,
            check=False,
            env={**os.environ, "PATH": search_path or ""},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "git"
    found = Path(done.stdout.decode("utf-8", "replace").strip()) / "git"
    if done.returncode == 0 and found.is_file() and os.access(found, os.X_OK):
        return str(found)
    return "git"


def redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


def _env(
    root: Path, writer: str | None, token: str | None, username: str | None = None
) -> dict[str, str]:
    env = dict(os.environ)
    for leftover in (
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "SSH_ASKPASS_REQUIRE",
        _TOKEN_ENV,
        _USERNAME_ENV,
        _PROTOCOL_ENV,
        _HOST_ENV,
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
        env[_USERNAME_ENV] = username or DEFAULT_USERNAME
    return env


def _origin_of(url: str) -> tuple[str, str] | None:
    """``(protocol, host[:port])`` as git's credential protocol spells them, for
    an http(s) remote URL; ``None`` for anything else (an ssh or local path)."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname if ":" not in parsed.hostname else f"[{parsed.hostname}]"
    port = parsed.port
    default = 443 if parsed.scheme == "https" else 80
    return parsed.scheme, host if port in (None, default) else f"{host}:{port}"


def _remote_origin(root: Path, args: tuple[str, ...]) -> tuple[str, str] | None:
    """The origin of the remote this call talks to: a URL it names, else the
    one the configured remote holds."""
    for arg in args:
        if "://" in arg and not arg.startswith("-"):
            return _origin_of(arg)
    configured = run(root, "config", "--get", "remote.origin.url", check=False)
    return _origin_of(text(configured).strip()) if configured.returncode == 0 else None


def run(
    root: Path,
    *args: str,
    check: bool = True,
    stdin: bytes | None = None,
    writer: str | None = None,
    literal: bool = False,
    token: str | None = None,
    username: str | None = None,
    timeout: float = LOCAL_TIMEOUT_S,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """``git <args>`` over the repository at ``root``, output captured.

    ``literal`` turns pathspec magic off, so a path is always the path it
    names. ``token`` adds the credential helper for a remote call.
    """
    argv = [_executable(os.environ.get("PATH")), *_PINNED]
    if token:
        argv += ["-c", "credential.helper=", "-c", f"credential.helper={_CREDENTIAL_HELPER}"]
    if literal:
        argv.append("--literal-pathspecs")
    argv += list(args)
    env = _env(root, writer, token, username)
    if token:
        origin = _remote_origin(root, args)
        if origin is not None:
            env[_PROTOCOL_ENV], env[_HOST_ENV] = origin
    if extra_env:
        env.update(extra_env)
    try:
        done = subprocess.run(
            argv,
            cwd=root if root.is_dir() else None,
            env=env,
            input=stdin if stdin is not None else b"",
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
