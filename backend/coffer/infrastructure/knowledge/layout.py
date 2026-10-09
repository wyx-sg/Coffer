"""Keeping a collection in its layout: Markdown documents left outside
``pages/`` and ``sources/`` are filed into ``pages/`` (spec knowledge "Sweep the
knowledge root on its mechanical duties").

A collection made before pages and sources existed holds its documents at the
root and in folders of its own; an agent that ignores the guide may write one
there too. Both are pages in all but place, so the sweep moves each to
``pages/<same relative path>`` and changes nothing in it. A file written in the
last minute is left for the next sweep, so a file still being written is never
moved from under its writer.
"""

from __future__ import annotations

import os
import pathlib
import time

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_collection_readme

#: How long a loose document must have been untouched before it is moved.
QUIET_SECONDS = 60.0

_KEPT = {paths.PAGES_DIR_NAME, paths.SOURCES_DIR_NAME}


def loose_documents(collection: str, *, now: float | None = None) -> list[str]:
    """Knowledge-root-relative paths of the Markdown files in ``collection``
    outside ``pages/``, ``sources/`` and hidden entries, other than its
    README, untouched for :data:`QUIET_SECONDS`."""
    root = paths.collection_dir(collection)
    if not root.is_dir():
        return []
    moment = time.time() if now is None else now
    found: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        here = pathlib.Path(current)
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and not (here == root and d in _KEPT)
        )
        for name in sorted(filenames):
            path = here / name
            if name.startswith(".") or not name.endswith(".md") or is_collection_readme(path):
                continue
            if path.is_symlink() or moment - path.stat().st_mtime < QUIET_SECONDS:
                continue
            found.append(paths.relative_of(path))
    return found


def file_into_pages(relpath: str) -> str:
    """Move one loose document to the same place under its collection's
    ``pages/``, suffixed ``-2``, ``-3``… when that name is taken; returns the
    new knowledge-root-relative path."""
    source = paths.resolve(relpath)
    collection, *rest = paths.split(relpath)
    directory = paths.pages_dir(collection).joinpath(*rest[:-1])
    stem = pathlib.Path(rest[-1]).stem
    target = directory / f"{stem}.md"
    n = 2
    while target.exists():
        target = directory / f"{stem}-{n}.md"
        n += 1
    directory.mkdir(parents=True, exist_ok=True)
    paths.assert_inside_root(target, paths.relative_of(target))
    source.rename(target)
    return paths.relative_of(target)


__all__ = ["QUIET_SECONDS", "file_into_pages", "loose_documents"]
