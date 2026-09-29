"""The port the application reaches the host operating system through.

Coffer's foundation must not hard-code macOS, even while the release is
macOS-only. So nothing in ``application/`` or ``domain/`` asks which OS it is
running on — ``scripts/check_platform_calls.py`` fails the build if one does.
Where a use case needs an answer that differs per OS (which paths are system
locations, which argv opens a file, where an editor is installed), it asks
this port, and the one adapter that knows the OS
(``coffer.infrastructure.platform.HostPlatform``) is handed in at the
composition root.

Only what an existing call site uses is here. A method answers a question; it
does not run anything — the application still owns spawning, validation and
error mapping, so the port stays a set of small lookups that a test can replace
with a fixed answer.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Protocol


@dataclasses.dataclass(frozen=True, slots=True)
class PrivilegedPaths:
    """Which locations count as the operating system's own.

    ``prefixes`` are matched at a component boundary (the entry itself, or the
    entry followed by ``separator``); anything under one of ``carve_outs`` is
    usable even when it nominally sits under a prefix. ``firmlink_root`` is the
    prefix some system roots are reached through (``/private`` on macOS:
    ``/etc`` is ``/private/etc``), stripped before matching so a resolved path
    cannot slip past the list; None where there is no such root.
    """

    prefixes: tuple[str, ...]
    carve_outs: tuple[str, ...]
    separator: str
    firmlink_root: str | None


class PlatformPort(Protocol):
    """What the application needs to know about the host operating system."""

    def os_label(self) -> str:
        """Human-readable OS name and release, e.g. ``"Darwin 24.6.0"``."""
        ...

    def privileged_paths(self) -> PrivilegedPaths:
        """The system locations an agent's skill directory must never be in."""
        ...

    def open_command(self, target: Path, with_app: str | None) -> list[str]:
        """The argv that opens an existing ``target`` in ``with_app`` or the default."""
        ...

    def reveal_command(self, target: Path) -> list[str]:
        """The argv that selects an existing ``target`` in the OS file manager."""
        ...

    def folder_picker_command(self, start: str | None) -> list[str] | None:
        """The argv of the native folder dialog, or None when the host has none."""
        ...

    def editor_launch_value(self, *, app_bundle: str | None, command: str | None) -> str | None:
        """The ``with_app`` value that launches an installed editor, or None.

        ``app_bundle`` is the editor's application-bundle name and ``command``
        its executable; which one applies, and how installation is detected,
        is the host's business.
        """
        ...
