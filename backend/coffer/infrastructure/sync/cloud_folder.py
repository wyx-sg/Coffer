"""Whether the vault sits inside a folder another tool synchronises
(ADR sync-applies-clean-merges-and-stops-on-any-conflict).

Syncthing, iCloud Drive, a File Provider root (Dropbox, Google Drive,
OneDrive on current macOS) and a classic Dropbox folder resolve by last
writer or a conflict copy, and would replicate the repository's internals
underneath git — so a vault in one is unsupported, and rounds pause until it
moves. Detection is by where the path is, never by asking the tool.
"""

from __future__ import annotations

from pathlib import Path

#: A marker file or folder that makes its directory the root of a synchronised
#: tree, and which tool it names.
_MARKERS = ((".stfolder", "Syncthing"), (".dropbox", "Dropbox"), (".dropbox.cache", "Dropbox"))
#: Roots, relative to the home directory, that are synchronised as a whole.
_ROOTS = (("Library/Mobile Documents", "iCloud Drive"), ("Library/CloudStorage", "a cloud drive"))


def synchroniser_of(path: Path, *, home: Path) -> str | None:
    """Which tool synchronises ``path`` ("Syncthing", "iCloud Drive", ...),
    or ``None`` when none does."""
    target = path.expanduser().resolve(strict=False)
    home = home.expanduser().resolve(strict=False)
    for rel, tool in _ROOTS:
        root = home / rel
        if target == root or root in target.parents:
            return tool
    for folder in (target, *target.parents):
        for marker, tool in _MARKERS:
            if (folder / marker).exists():
                return tool
    return None


__all__ = ["synchroniser_of"]
