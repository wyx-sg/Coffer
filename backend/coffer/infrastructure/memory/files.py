"""Listing a partition's directory as a file tree (spec memory "Show a partition's memories
read-only").

The partition surface shows Coffer's own writing as it is on disk: ``MEMORY.md``,
the ``notes/`` folder of one Markdown file per topic, and ``RETIRED.md`` when
anything has been retired. The hidden ``.raw/`` that aggregation wrote is left
out of the tree: it is dozens of hash-named files of verbatim agent input that
crowd out the notes, and it is not Coffer's answer to anything. An agent never
reads it either: recall and delivery go through ``notes/`` alone.

The tree is derived (see "Keep the memory tree derived and local") and the next
pass would overwrite any edit, so this module reads and never writes. Reading a
file's text is not done here: the web page shows the tree, and a note's text
comes from the note itself, or from the file on disk.

Every other hidden entry is left out too: the only ones that occur are the
``.<name>.tmp`` files an atomic write leaves for a few milliseconds, which would
show a half-written file as though it were content.

Containment: every entry is resolved and must stay inside the resolved
partition directory. A symlink whose target escapes is skipped, and symlinked
directories are never descended into, so a cycle cannot send the walk into a
loop.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Literal

#: Ceiling on walk depth. A partition is two levels deep by construction, so
#: anything near this is a tree Coffer did not build; stopping is cheaper than
#: letting Python's own recursion limit turn it into a 500.
MAX_TREE_DEPTH = 16


@dataclass
class FileNode:
    """One entry in a partition's tree.

    ``path`` is POSIX and relative to the partition directory (``""`` for the
    root node itself), because that is what the surface hands back on a read;
    ``size`` is ``None`` for a directory.
    """

    name: str
    path: str
    type: Literal["file", "dir"]
    size: int | None = None
    children: list[FileNode] = field(default_factory=list)
    #: Set on a directory whose descendants were clipped at ``MAX_TREE_DEPTH``,
    #: so the surface can say the tree was cut rather than show it as empty.
    truncated: bool = False


def _is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def build_tree(partition_dir: pathlib.Path) -> FileNode:
    """Walk ``partition_dir`` into a recursive, read-only tree.

    The root node carries ``path == ""`` and the directory's own name. A
    partition whose directory does not exist yet — aggregation registered the
    Resource but has not written into it — yields an empty root rather than an
    error, because "this partition holds nothing yet" is a normal state the
    surface must be able to render.
    """
    root = partition_dir.resolve()
    node = FileNode(name=root.name, path="", type="dir")
    node.children = _children(root, root, depth=0)
    return node


def _children(directory: pathlib.Path, root: pathlib.Path, *, depth: int) -> list[FileNode]:
    nodes: list[FileNode] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        # An unreadable directory shows as empty rather than failing the whole
        # tree; a read of anything under it still reports its own error.
        return nodes

    for entry in entries:
        if not _is_listable(entry.name):
            continue
        try:
            if entry.is_symlink() and not _is_within(entry.resolve(strict=False), root):
                continue
            rel = entry.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue

        if entry.is_dir() and not entry.is_symlink():
            child = FileNode(name=entry.name, path=rel, type="dir")
            if depth + 1 >= MAX_TREE_DEPTH:
                child.truncated = True
            else:
                child.children = _children(entry, root, depth=depth + 1)
            nodes.append(child)
        elif entry.is_file():
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            nodes.append(FileNode(name=entry.name, path=rel, type="file", size=size))
        # Sockets, fifos and symlinked directories are deliberately omitted:
        # only real files and real directories are addressable here.

    # Directories first, then by name.
    nodes.sort(key=lambda n: (n.type != "dir", n.name))
    return nodes


def _is_listable(name: str) -> bool:
    """Is this entry addressable through the tree at all?

    No hidden name is: ``.raw/`` is aggregation's verbatim input rather than
    Coffer's writing, and the only other ones that occur are the
    ``.<name>.tmp`` files an atomic write leaves behind for a moment, which a
    surface would show as the partition's content mid-rewrite.
    """
    return not name.startswith(".")


__all__ = [
    "MAX_TREE_DEPTH",
    "FileNode",
    "build_tree",
]
