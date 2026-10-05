"""A skill folder's content, as one digest.

What a Git-imported skill is pinned to is a commit *and* the content that
commit gave its folder (spec skill-manager "Hand a Git-imported skill's update
to an agent"). Comparing the master folder's digest with the pinned one is how
Coffer knows the person edited the skill since the pin, without keeping a
checkout of the pinned commit around.

The digest is SHA-256 over every regular file's folder-relative POSIX path and
bytes, in path order, each framed by its length so no two different trees can
serialise alike. Coffer's own bookkeeping file and a ``.git`` directory are not
content. A symlink contributes its target text, not what it points at.
"""

from __future__ import annotations

import hashlib
import os
import pathlib

#: Not part of a skill's content: Coffer's own metadata file in the master
#: folder, and version-control state the store never copies.
IGNORED_NAMES = frozenset({".coffer.meta.json", ".git"})


def iter_content_files(folder: pathlib.Path) -> list[str]:
    """Every content file's folder-relative POSIX path, sorted."""
    out: list[str] = []
    for root, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_NAMES]
        base = pathlib.Path(root)
        for name in filenames:
            if name in IGNORED_NAMES and base == folder:
                continue
            out.append((base / name).relative_to(folder).as_posix())
        for d in dirnames:
            entry = base / d
            if entry.is_symlink():
                out.append(entry.relative_to(folder).as_posix())
    return sorted(set(out))


def folder_content_hash(folder: pathlib.Path) -> str:
    """The SHA-256 hex digest of ``folder``'s content (see module doc)."""
    h = hashlib.sha256()
    for rel in iter_content_files(folder):
        entry = folder / rel
        if entry.is_symlink():
            data = b"link:" + os.readlink(entry).encode("utf-8", "surrogateescape")
        else:
            data = entry.read_bytes()
        name = rel.encode("utf-8", "surrogateescape")
        h.update(len(name).to_bytes(8, "big"))
        h.update(name)
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


__all__ = ["IGNORED_NAMES", "folder_content_hash", "iter_content_files"]
