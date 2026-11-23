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


#: Wrapped around ``$PATH`` in the probe's output, so a profile that prints
#: something (a greeting, a version manager's notice) cannot spoil the value.
_PATH_MARKER = "__COFFER_PATH__"

#: The probes, most complete first. An interactive login shell (``-ilc``)
#: also reads ``~/.zshrc`` / ``~/.bashrc``, where nvm, fnm, pyenv and most
#: installers put their PATH lines; a login-only shell reads just
#: ``~/.zprofile``. VS Code resolves a GUI launch's environment the same way.
#: A profile that fails interactively still gets the login-only answer.
_SHELL_PROBES = ("-ilc", "-lc")


def login_shell_path() -> str:
    """The user's real ``PATH``, as their shell in a terminal reports it.

    Not ``os.environ["PATH"]``, and the difference is the point. This code
    usually runs *inside the daemon*, which is commonly auto-spawned by an MCP
    shim belonging to a GUI-launched editor, whose ``PATH`` is the truncated one
    macOS hands a Dock launch. The user's shell knows where their tools
    really are (``~/.local/bin``, Homebrew, a Node version manager).

    POSIX asks the shell the same way ``desktop/src/env_path.rs`` does;
    Windows has no login shell and its inherited ``PATH`` is already the
    user's. Any failure falls back to the inherited value: a probe that cannot
    answer must not stop its caller.
    """
    inherited = os.environ.get("PATH", "")
    if host_os() is HostOs.WINDOWS:
        return inherited
    shell = os.environ.get("SHELL", "/bin/zsh")
    for flags in _SHELL_PROBES:
        probed = _probe_path(shell, flags)
        if probed:
            return probed
    return inherited


def _probe_path(shell: str, flags: str) -> str | None:
    probe = f"printf '%s%s%s' '{_PATH_MARKER}' \"$PATH\" '{_PATH_MARKER}'"
    try:
        result = subprocess.run(
            [shell, flags, probe],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_SHELL_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("shell PATH probe %s failed (%r)", flags, exc)
        return None
    return _extract_marked_path(result.stdout)


def _extract_marked_path(output: str) -> str | None:
    """The ``PATH`` between the probe's markers, or None when they are missing."""
    start = output.find(_PATH_MARKER)
    if start < 0:
        return None
    start += len(_PATH_MARKER)
    end = output.find(_PATH_MARKER, start)
    if end < 0:
        return None
    return output[start:end].strip() or None
