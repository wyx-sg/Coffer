"""Read-only local-filesystem browsing for the skill-directory folder picker.

Spec 004-agent-registry FR-024. Lists the immediate subdirectories of a
directory so the web folder browser can navigate the user's filesystem and
hand back an absolute path (the daemon, unlike a browser, can read real
paths). It never returns file contents — directories only.

Filesystem reads in the application layer are already precedented here (see
``AgentService.assert_skill_dir_usable``), so this service uses ``pathlib`` /
``os.scandir`` directly rather than going through an infrastructure port.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from coffer.domain.errors import FsPathNotBrowsable


@dataclass(frozen=True)
class FsEntry:
    name: str
    path: str


@dataclass(frozen=True)
class FsBrowseResult:
    path: str
    parent: str | None
    entries: list[FsEntry]


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


class FsBrowseService:
    """List subdirectories of a directory (defaults to the user's home)."""

    def browse(self, path: str | None = None) -> FsBrowseResult:
        base = pathlib.Path(path).expanduser() if path else _home()
        try:
            resolved = base.resolve()
        except OSError as e:  # pragma: no cover — exotic FS errors
            raise FsPathNotBrowsable(str(base), "unresolvable") from e
        if not resolved.is_dir():
            raise FsPathNotBrowsable(str(resolved), "not_a_directory")
        try:
            # Hidden directories (e.g. ~/.claude, ~/.codex) MUST be listed —
            # they're exactly the config folders the user is browsing for.
            children = sorted(
                (e for e in os.scandir(resolved) if _is_dir(e)),
                key=lambda e: e.name.lower(),
            )
        except OSError as e:
            raise FsPathNotBrowsable(str(resolved), "not_readable") from e
        # The filesystem root is its own parent; report None there so the UI
        # can hide the "up" affordance.
        parent = str(resolved.parent) if resolved.parent != resolved else None
        return FsBrowseResult(
            path=str(resolved),
            parent=parent,
            entries=[FsEntry(name=e.name, path=e.path) for e in children],
        )


def _is_dir(entry: os.DirEntry[str]) -> bool:
    # Do not follow symlinks — a symlinked dir is still navigable, but resolving
    # it here would let a link masquerade and could loop. The browse() of the
    # target path resolves it explicitly when the user navigates in.
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:  # pragma: no cover — race: entry vanished mid-scan
        return False
