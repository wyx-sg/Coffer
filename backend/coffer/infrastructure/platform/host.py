"""Which operating system this process runs on — the one place that asks.

Every other module in Coffer that behaves differently per OS goes through this
package; ``scripts/check_platform_calls.py`` fails the build on a
``sys.platform`` / ``platform.system()`` / ``os.name`` check anywhere else.

The answer is read on every call rather than cached, so a test that pins
``sys.platform`` sees the adapter follow it.
"""

from __future__ import annotations

import platform
import sys
from enum import Enum


class HostOs(Enum):
    """The operating systems Coffer distinguishes between."""

    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    #: Any other POSIX host. Treated like Linux wherever a branch exists.
    OTHER = "other"


def host_os() -> HostOs:
    """The host's OS family, read from ``sys.platform``."""
    if sys.platform == "darwin":
        return HostOs.MACOS
    if sys.platform == "win32":
        return HostOs.WINDOWS
    if sys.platform.startswith("linux"):
        return HostOs.LINUX
    return HostOs.OTHER


def os_label() -> str:
    """The OS name and release as a person reads them, e.g. ``"Darwin 24.6.0"``."""
    return f"{platform.system()} {platform.release()}".strip()


def machine_label() -> str:
    """The OS and CPU architecture as an agent needs them to pick an install
    method, e.g. ``"macOS 15.6, arm64"`` or ``"Ubuntu 24.04 LTS, x86_64"``."""
    arch = platform.machine() or "unknown architecture"
    return f"{_os_name()}, {arch}"


def _os_name() -> str:
    family = host_os()
    if family is HostOs.MACOS:
        release = platform.mac_ver()[0]
        return f"macOS {release}" if release else "macOS"
    if family is HostOs.WINDOWS:
        return f"Windows {platform.release()}".strip()
    if family is HostOs.LINUX:
        try:
            pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
        except OSError:
            pretty = None
        if pretty:
            return pretty
    return os_label() or "an unknown operating system"
