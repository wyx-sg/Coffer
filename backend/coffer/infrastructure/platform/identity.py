"""The host's own stable machine identifier, where the OS keeps one.

* **macOS** — ``IOPlatformUUID``, held by the ``IOPlatformExpertDevice`` node.
  Tied to the hardware; survives reinstalling the OS.
* **Linux** — ``/etc/machine-id``, falling back to ``/var/lib/dbus/machine-id``
  on systems where systemd is not the one keeping it.

Anything else answers None, and the caller falls back to an identifier of its
own (``coffer.infrastructure.sync.machine_id``). The raw value is returned
as-is; hashing it before it leaves the machine is the caller's job.
"""

from __future__ import annotations

import pathlib
import subprocess

from coffer.infrastructure.platform.host import HostOs, host_os

_IOREG = ("ioreg", "-rd1", "-c", "IOPlatformExpertDevice")
LINUX_SOURCES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
_TIMEOUT_S = 5.0


def os_machine_id() -> str | None:
    """The OS-kept machine identifier, or None when this host keeps none."""
    system = host_os()
    if system is HostOs.MACOS:
        return _macos_platform_uuid()
    if system is HostOs.LINUX:
        return _first_readable(LINUX_SOURCES)
    return None


def _macos_platform_uuid() -> str | None:
    """Parse ``IOPlatformUUID`` out of ioreg's plain-text dump.

    ioreg is on every macOS; a missing binary or a changed output shape falls
    through to the caller's fallback rather than failing the daemon's start.
    """
    try:
        done = subprocess.run(
            _IOREG, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    for line in done.stdout.splitlines():
        if "IOPlatformUUID" not in line:
            continue
        # `      "IOPlatformUUID" = "1E4C…"`
        parts = line.split('"')
        if len(parts) >= 4 and parts[-2].strip():
            return parts[-2].strip()
    return None


def _first_readable(paths: tuple[str, ...]) -> str | None:
    for path in paths:
        try:
            value = pathlib.Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return None
