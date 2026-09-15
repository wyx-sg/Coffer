"""Reading a partition's directory as a file tree (spec memory FR-062).

The partition surface shows what is actually on disk: the ``README.md`` that
says which project the partition was named from, the ``summary.md`` organise
rewrites, and the ``facts/`` folder of one Markdown file per fact. There is
nothing to edit here — the whole tree is derived (FR-023) and the next
aggregation pass would overwrite an edit anyway — so this module reads and
never writes. That is also why a file's content carries no fingerprint: a
fingerprint exists to make a later write conditional, and there is no write.

Why memory grows its own reader rather than borrowing the skill kind's
``application/skill/file_ops.py``, which walks a directory the same way: the
import-linter contract in ``backend/pyproject.toml`` fences each kind off from
every other, and file_ops is the skill kind's, not shared substrate. The two
readers also want different things — skill's serves an editor and must
fingerprint bytes and follow its own 50 MB folder cap, this one serves a
preview over a tree of small Markdown files — so what looks like duplication
is two short readers with different jobs, which this codebase already prefers
to one coupling (``application/memory/recall.py``'s own docstring makes the
same call about knowledge's ripgrep).

Containment is enforced the way ``paths.check_segment`` guards a partition
name (FR-072): every candidate is resolved and must stay inside the resolved
partition directory. A symlink whose target escapes is skipped from the tree
and refused on read, and symlinked directories are never descended into, so a
cycle cannot send the walk into a loop.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from coffer.domain.error_base import CofferError
from coffer.infrastructure.memory.paths import UnsafeMemoryPath

#: Cap on a single read. A fact file is a few hundred bytes and a digest a few
#: kilobytes, so this is never reached in practice; it is here so that a file
#: something else dropped into the tree cannot make the response unbounded.
MAX_FILE_BYTES = 256 * 1024

#: Ceiling on walk depth. A partition is two levels deep by construction, so
#: anything near this is a tree Coffer did not build; stopping is cheaper than
#: letting Python's own recursion limit turn it into a 500.
MAX_TREE_DEPTH = 16


class MemoryFileNotFound(CofferError):  # noqa: N818
    """No readable file at that path inside the partition."""

    code = "MEMORY_FILE_NOT_FOUND"

    def __init__(self, partition: str, relpath: str) -> None:
        super().__init__(f"no such file in memory partition {partition!r}: {relpath}")
        self.partition = partition
        self.relpath = relpath


@dataclass
class FileNode:
    """One entry in a partition's tree.

    ``path`` is POSIX and relative to the partition directory (``""`` for the
    root node itself), because that is what the surface hands back on a read;
    ``size`` is ``None`` for a directory.
    """

    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    children: list[FileNode] = field(default_factory=list)
    #: Set on a directory whose descendants were clipped at ``MAX_TREE_DEPTH``,
    #: so the surface can say the tree was cut rather than show it as empty.
    truncated: bool = False


@dataclass(frozen=True)
class FileContent:
    """One file's text, or the fact that it is not text.

    A file that is not valid UTF-8, or that holds a NUL byte, comes back with
    ``binary`` set and ``content`` empty rather than with mojibake: the
    surface renders a placeholder for it, and ``size`` still says how big the
    thing on disk is.
    """

    path: str
    content: str
    truncated: bool
    binary: bool
    size: int


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

    nodes.sort(key=lambda n: (n.type != "dir", n.name))
    return nodes


def read_file(partition: str, partition_dir: pathlib.Path, relpath: str) -> FileContent:
    """Read one file under ``partition_dir``.

    Raises:
        UnsafeMemoryPath: ``relpath`` resolves outside the partition — checked
            before anything is opened, so an escape never reads a byte.
        MemoryFileNotFound: nothing readable is there, including the case of
            ``relpath`` naming the partition directory itself.
    """
    root = partition_dir.resolve()
    candidate = (root / relpath).resolve(strict=False)
    if not _is_within(candidate, root):
        raise UnsafeMemoryPath(relpath, "path escapes the partition directory")
    if candidate == root or not candidate.is_file():
        raise MemoryFileNotFound(partition, relpath)

    size = candidate.stat().st_size
    # One byte past the cap, so the read stays bounded whatever the file's true
    # length is and that extra byte still says whether it overflowed.
    with candidate.open("rb") as fh:
        read = fh.read(MAX_FILE_BYTES + 1)
    truncated = len(read) > MAX_FILE_BYTES
    chunk = read[:MAX_FILE_BYTES] if truncated else read
    rel = candidate.relative_to(root).as_posix()

    if b"\x00" in chunk:
        return FileContent(path=rel, content="", truncated=truncated, binary=True, size=size)
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        if truncated:
            # The cut may have split a trailing multi-byte sequence, which does
            # not make the file binary — decode the valid prefix and drop the
            # dangling bytes rather than mislabel a large text file.
            return FileContent(
                path=rel,
                content=chunk.decode("utf-8", errors="ignore"),
                truncated=True,
                binary=False,
                size=size,
            )
        return FileContent(path=rel, content="", truncated=truncated, binary=True, size=size)
    return FileContent(path=rel, content=text, truncated=truncated, binary=False, size=size)


__all__ = [
    "MAX_FILE_BYTES",
    "MAX_TREE_DEPTH",
    "FileContent",
    "FileNode",
    "MemoryFileNotFound",
    "build_tree",
    "read_file",
]
