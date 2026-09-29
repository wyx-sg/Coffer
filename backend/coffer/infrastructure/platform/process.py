"""Per-OS process facts: executable names, detaching a child, the login-service manager."""

from __future__ import annotations

import subprocess

from coffer.infrastructure.platform.host import HostOs, host_os


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
