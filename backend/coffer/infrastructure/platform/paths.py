"""Which locations are the operating system's own (privileged-path defence)."""

from __future__ import annotations

import os

from coffer.application.platform_port import PrivilegedPaths
from coffer.infrastructure.platform.host import HostOs, host_os

PRIVILEGED_PREFIXES_POSIX = (
    "/etc",
    "/bin",
    "/sbin",
    "/usr",
    "/var",
    "/sys",
    "/proc",
    "/root",
    "/boot",
    "/dev",
    "/System",
    "/Library/Application Support/Apple",
)
# Carve-outs INSIDE a privileged prefix that should still be usable. macOS's
# user temp area lives under ``/var/folders/<hash>`` (resolved from the
# /private firmlink); tests and ad-hoc tooling routinely place skills there.
PRIVILEGED_CARVE_OUTS_POSIX = ("/var/folders/",)
PRIVILEGED_PREFIXES_WIN = (
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
)
#: macOS reaches several system roots through this firmlink (``/etc`` →
#: ``/private/etc``, ``/var`` → ``/private/var``).
MACOS_FIRMLINK_ROOT = "/private"


def privileged_paths() -> PrivilegedPaths:
    """The privileged-location rules for this host."""
    system = host_os()
    if system is HostOs.WINDOWS:
        return PrivilegedPaths(
            prefixes=PRIVILEGED_PREFIXES_WIN,
            carve_outs=(),
            separator="\\",
            firmlink_root=None,
        )
    return PrivilegedPaths(
        prefixes=PRIVILEGED_PREFIXES_POSIX,
        carve_outs=PRIVILEGED_CARVE_OUTS_POSIX,
        separator=os.sep,
        firmlink_root=MACOS_FIRMLINK_ROOT if system is HostOs.MACOS else None,
    )
