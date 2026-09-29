"""Per-OS process facts: executable names, the user's real ``PATH``, detaching a
child, the login-service manager."""

from __future__ import annotations

import logging
import os
import subprocess

from coffer.infrastructure.platform.host import HostOs, host_os

_logger = logging.getLogger(__name__)

#: How long the login-shell probe is allowed to take. A shell profile that
#: hangs must not hang its caller; the inherited PATH is a worse answer, not
#: no answer.
_SHELL_PROBE_TIMEOUT = 3.0


def executable_name(stem: str) -> str:
    """``stem`` as this host names an executable (``.exe`` on Windows)."""
    return f"{stem}.exe" if host_os() is HostOs.WINDOWS else stem


def has_app_bundles() -> bool:
    """True where programs are installed as ``.app`` bundles (macOS)."""
    return host_os() is HostOs.MACOS


def has_launchd() -> bool:
    """True where launchd manages per-user login agents (macOS)."""
    return host_os() is HostOs.MACOS


def detached_popen_kwargs() -> dict[str, object]:
    """The ``Popen`` keywords that let a child outlive the process that spawned it.

    Windows: no console window, detached from the parent's console. POSIX: a new
    session, so the child survives the parent's terminal and process group.
    """
    if host_os() is HostOs.WINDOWS:
        return {
            "creationflags": (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            )
        }
    return {"start_new_session": True}


def login_shell_path() -> str:
    """The user's real ``PATH``, as their login shell reports it.

    Not ``os.environ["PATH"]``, and the difference is the point. This code
    usually runs *inside the daemon*, which is commonly auto-spawned by an MCP
    shim belonging to a GUI-launched editor, whose ``PATH`` is the truncated one
    macOS hands a Dock launch. The login shell knows where the user's tools
    really are (``~/.local/bin``, Homebrew, a Node version manager).

    POSIX asks the login shell the same way ``desktop/src/env_path.rs`` does;
    Windows has no login shell and its inherited ``PATH`` is already the
    user's. Any failure falls back to the inherited value: a probe that cannot
    answer must not stop its caller.
    """
    inherited = os.environ.get("PATH", "")
    if host_os() is HostOs.WINDOWS:
        return inherited
    shell = os.environ.get("SHELL", "/bin/zsh")
    try:
        result = subprocess.run(
            [shell, "-l", "-c", 'printf %s "$PATH"'],
            capture_output=True,
            text=True,
            timeout=_SHELL_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("login shell PATH probe failed (%r); using the inherited PATH", exc)
        return inherited
    probed = result.stdout.strip()
    return probed or inherited
