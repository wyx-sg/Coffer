"""Desktop applications installed the way the operating system keeps them.

An agent product can ship as a desktop app without its command-line program
(the Antigravity App without ``agy``). The dependency probe asks this module
for the app bundle when the program is not on the agent's ``PATH``
(spec agent-registry "Detect an agent by its program and its config
directory"). Only macOS keeps apps as bundles Coffer can find by name; every
other host answers ``None``.
"""

from __future__ import annotations

import os
import pathlib
import plistlib
from dataclasses import dataclass

from coffer.infrastructure.platform.host import HostOs, host_os


@dataclass(frozen=True)
class InstalledApp:
    path: pathlib.Path
    version: str | None


def _roots() -> tuple[pathlib.Path, ...]:
    home = pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))
    return (pathlib.Path("/Applications"), home / "Applications")


def find_app_bundle(
    bundle: str, *, roots: tuple[pathlib.Path, ...] | None = None
) -> InstalledApp | None:
    """The bundle named ``bundle`` (``Antigravity.app``) in the system or the
    user's Applications folder, with the version its ``Info.plist`` declares;
    ``None`` when it is not there or the host keeps no app bundles."""
    if roots is None:
        if host_os() is not HostOs.MACOS:
            return None
        roots = _roots()
    for root in roots:
        path = root / bundle
        if path.is_dir():
            return InstalledApp(path=path, version=_bundle_version(path))
    return None


def _bundle_version(path: pathlib.Path) -> str | None:
    try:
        with (path / "Contents" / "Info.plist").open("rb") as fh:
            info = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    version = info.get("CFBundleShortVersionString") if isinstance(info, dict) else None
    return version if isinstance(version, str) and version else None


__all__ = ["InstalledApp", "find_app_bundle"]
