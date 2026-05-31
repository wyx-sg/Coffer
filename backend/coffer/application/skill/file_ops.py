"""Read-only file-tree + file-content helpers for a skill's master folder.

A skill's canonical master folder lives at ``~/.coffer/skills/<name>/`` and is
Coffer-owned (see ``infrastructure/skill/master_store.py``). Surfaces show that
folder as a file tree and let the user read individual files, read-only.

This is a "helper module beside ``service.py``" (like ``verify_ops.py`` and
``update_ops.py``): free functions, no class state. They are pure-ish reads of
the filesystem — no mutation, no DB, no audit — so they take a resolved
``pathlib.Path`` rather than the ``SkillService`` instance.

Containment is enforced the same way ``domain/skill/validator.py`` guards
imports: every candidate path is resolved and must stay inside the (resolved)
master folder. A symlink whose real target escapes the folder is skipped from
the tree and rejected (``ValueError``) when read. Symlinked directories are
never followed (``os.walk`` is not used; we recurse explicitly and inspect
each entry), so a cyclic symlink cannot send the recursion into a loop.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from coffer.domain.skill.paths import is_within

# Cap a single file read at 256 KiB. Larger files are truncated to the first
# 256 KiB with ``truncated=True`` so the viewer stays responsive and the wire
# payload bounded; the master folder itself already has a 50 MB total cap.
MAX_FILE_BYTES = 256 * 1024

# Ceiling on tree-walk recursion depth. A skill folder this deep is pathological
# (or hostile); beyond it we stop descending rather than let Python's recursion
# limit raise ``RecursionError`` and 500 the request. The deepest level is
# marked ``truncated=True`` so the surface can signal the tree was clipped.
MAX_TREE_DEPTH = 64


@dataclass
class FileNode:
    """One entry in a skill's master folder tree.

    ``path`` is POSIX-style and relative to the master folder root (``""`` for
    the root node). ``size`` is the file's byte size (``None`` for directories).
    ``children`` is populated for directories and empty for files.
    """

    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    children: list[FileNode] = field(default_factory=list)
    # Set on a directory whose descendants were clipped at ``MAX_TREE_DEPTH``.
    truncated: bool = False


@dataclass(frozen=True)
class FileContent:
    """A single skill file's contents (read-only)."""

    path: str
    content: str
    truncated: bool
    binary: bool
    size: int


def build_file_tree(master_folder: pathlib.Path) -> FileNode:
    """Build a recursive read-only tree of ``master_folder``.

    The returned root node has ``path == ""`` and ``name`` equal to the folder
    name. Each child records its name, POSIX relative path, type, file size,
    and (for directories) children. Entries are sorted directories-first then
    by name. Any symlink whose resolved target escapes ``master_folder`` is
    skipped; symlinked directories are not descended into.
    """
    root = master_folder.resolve()
    node = FileNode(name=root.name, path="", type="dir")
    node.children = _build_children(root, root, depth=0)
    return node


def _build_children(directory: pathlib.Path, root: pathlib.Path, *, depth: int) -> list[FileNode]:
    children: list[FileNode] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        # Unreadable directory — surface as empty rather than crashing the
        # whole tree. A read of any file under it will still 404 / error.
        return children

    for entry in entries:
        try:
            # A symlink that escapes the folder must never appear in the tree.
            if entry.is_symlink():
                target = entry.resolve(strict=False)
                if not is_within(target, root):
                    continue
            rel = entry.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            # Broken/unreadable link or a target outside root — skip it.
            continue

        if entry.is_dir() and not entry.is_symlink():
            child = FileNode(name=entry.name, path=rel, type="dir")
            if depth + 1 >= MAX_TREE_DEPTH:
                # Stop descending past the bound. Mark the node so the caller
                # knows its children were clipped rather than genuinely empty.
                child.truncated = True
            else:
                child.children = _build_children(entry, root, depth=depth + 1)
            children.append(child)
        elif entry.is_file():
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            children.append(FileNode(name=entry.name, path=rel, type="file", size=size))
        # Anything else (sockets, fifos, symlinked dirs) is intentionally
        # omitted — only real files and real directories are listed.

    # Directories first, then files; each group sorted by name.
    children.sort(key=lambda n: (n.type != "dir", n.name))
    return children


def read_skill_file(master_folder: pathlib.Path, relpath: str) -> FileContent:
    """Read a single file under ``master_folder``.

    ``relpath`` is interpreted relative to ``master_folder``. The resolved
    target MUST stay inside the (resolved) master folder; an escape (``..``,
    an absolute path, or a symlink pointing out) raises ``ValueError``. Reads
    are capped at ``MAX_FILE_BYTES`` (sets ``truncated=True``). A file that is
    not valid UTF-8 or contains a NUL byte is reported as ``binary=True`` with
    empty ``content``.

    Raises:
        ValueError: ``relpath`` resolves outside the master folder.
        FileNotFoundError: no regular file exists at the resolved path.
    """
    root = master_folder.resolve()
    candidate = (root / relpath).resolve(strict=False)
    if not is_within(candidate, root):
        raise ValueError(f"path escapes skill folder: {relpath!r}")
    # The root itself is a directory, not a readable file.
    if candidate == root:
        raise FileNotFoundError(relpath)
    if not candidate.is_file():
        raise FileNotFoundError(relpath)

    size = candidate.stat().st_size
    # Read at most MAX_FILE_BYTES+1 so memory stays bounded regardless of the
    # true file size; the extra byte tells us whether the file overflows the
    # cap. ``size`` (from stat) still reports the full length on the wire.
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
            # The 256 KiB cut may have split a trailing multi-byte UTF-8
            # sequence; that alone doesn't make the file binary. Decode the
            # valid prefix and drop the dangling bytes rather than mislabel a
            # large text file as binary.
            text = chunk.decode("utf-8", errors="ignore")
            return FileContent(path=rel, content=text, truncated=True, binary=False, size=size)
        return FileContent(path=rel, content="", truncated=truncated, binary=True, size=size)
    return FileContent(path=rel, content=text, truncated=truncated, binary=False, size=size)
