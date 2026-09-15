"""Reading one native-memory store's directory as a tree and its files as text.

The scan (``native_memory_store.py``) answers "which stores exist and how big";
this answers "what is actually in this one". Together they are what makes the
agent's own memory inspectable without leaving Coffer: the list says a project
has 41 facts, and this shows the reader the 41 files and what each one says.

Read-only throughout. These bytes belong to the coding agent, which rewrites
them whenever it learns something; an edit made here would be a change with a
countdown on it, silently reverted with nothing to tell the reader it had
happened. Opening the file in a real editor is the honest way to change it, and
the surface offers that instead.

Why the agent kind grows its own short reader rather than borrowing the skill
kind's ``application/skill/file_ops.py`` or the memory kind's
``infrastructure/memory/files.py``, both of which walk a directory the same way:
the import-linter contracts in ``backend/pyproject.toml`` fence each kind off
from every other, and neither of those is shared substrate. The jobs differ too
— skill's reader serves an editor and must fingerprint bytes for conditional
writes; this one serves a preview over a tree nobody writes — so what looks like
duplication is short readers with different obligations, which this codebase
already prefers to one coupling.

Containment is enforced the way the skill and memory readers enforce theirs:
every candidate is resolved and must stay inside the resolved store directory. A
symlink whose target escapes is skipped from the tree and refused on read, and
symlinked directories are never descended into, so a cycle cannot send the walk
into a loop.
"""

from __future__ import annotations

import pathlib

from coffer.domain.agent.native_memory import MemoryFileContent, MemoryFileNode

#: Cap on a single read. A memory fact file is a few hundred bytes and an index
#: a few kilobytes, so this is never reached by anything Coffer put there; it is
#: here so that a file something else dropped into the store cannot make the
#: response unbounded.
MAX_FILE_BYTES = 256 * 1024

#: Ceiling on walk depth. A store is one level deep by construction, so anything
#: near this is a tree the agent did not build; stopping is cheaper than letting
#: Python's own recursion limit turn it into a 500.
MAX_TREE_DEPTH = 16


def _is_within(candidate: pathlib.Path, root: pathlib.Path) -> bool:
    """Whether *candidate* (resolved) stays inside *root* (resolved)."""
    return candidate == root or root in candidate.parents


def build_tree(store_dir: pathlib.Path) -> MemoryFileNode:
    """Build a recursive read-only tree of *store_dir*.

    The root node has ``path == ""`` and the directory's own name. Entries are
    sorted directories-first then by name, so a reader's eye lands in the same
    place in every store. A store directory that does not exist comes back as an
    empty root rather than an error: the agent may simply not have written to
    that project yet, and an empty tree says so more usefully than a 404.
    """
    root = store_dir.resolve()
    node = MemoryFileNode(name=root.name, path="", type="dir")
    node.children = _children(root, root, depth=0)
    return node


def _children(directory: pathlib.Path, root: pathlib.Path, *, depth: int) -> list[MemoryFileNode]:
    out: list[MemoryFileNode] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        # Unreadable (or absent) directory — surface as empty rather than
        # crashing the whole tree. Reading anything under it still errors.
        return out

    for entry in entries:
        try:
            # A symlink that escapes the store must never appear in the tree.
            if entry.is_symlink() and not _is_within(entry.resolve(strict=False), root):
                continue
            rel = entry.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            # Broken/unreadable link, or a target outside the root — skip it.
            continue

        if entry.is_dir() and not entry.is_symlink():
            child = MemoryFileNode(name=entry.name, path=rel, type="dir")
            if depth + 1 >= MAX_TREE_DEPTH:
                # Stop descending past the bound, and say the children were
                # clipped rather than let the node read as genuinely empty.
                child.truncated = True
            else:
                child.children = _children(entry, root, depth=depth + 1)
            out.append(child)
        elif entry.is_file():
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            out.append(MemoryFileNode(name=entry.name, path=rel, type="file", size=size))
        # Anything else (sockets, fifos, symlinked dirs) is intentionally
        # omitted — only real files and real directories are listed.

    out.sort(key=lambda n: (n.type != "dir", n.name))
    return out


def read_file(store_dir: pathlib.Path, relpath: str) -> MemoryFileContent:
    """Read one file under *store_dir*.

    Reads are capped at :data:`MAX_FILE_BYTES` (``truncated=True`` past it). A
    file that is not valid UTF-8 or carries a NUL byte is reported as
    ``binary=True`` with empty content rather than guessed at.

    Raises:
        ValueError: *relpath* resolves outside the store directory.
        FileNotFoundError: no regular file exists at the resolved path.
    """
    root = store_dir.resolve()
    candidate = (root / relpath).resolve(strict=False)
    if not _is_within(candidate, root):
        raise ValueError(f"path escapes the memory store: {relpath!r}")
    if candidate == root or not candidate.is_file():
        raise FileNotFoundError(relpath)

    size = candidate.stat().st_size
    # Read at most the cap plus one byte, so memory stays bounded whatever the
    # real size is; the extra byte is what tells us the file overflowed.
    # ``size`` from stat still reports the true length on the wire.
    with candidate.open("rb") as fh:
        read = fh.read(MAX_FILE_BYTES + 1)
    truncated = len(read) > MAX_FILE_BYTES
    chunk = read[:MAX_FILE_BYTES] if truncated else read
    rel = candidate.relative_to(root).as_posix()

    if b"\x00" in chunk:
        return MemoryFileContent(path=rel, content="", truncated=truncated, binary=True, size=size)
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        if truncated:
            # The cut may have split a trailing multi-byte sequence; that alone
            # does not make the file binary. Decode the valid prefix and drop
            # the dangling bytes rather than mislabel a large text file.
            return MemoryFileContent(
                path=rel,
                content=chunk.decode("utf-8", errors="ignore"),
                truncated=True,
                binary=False,
                size=size,
            )
        return MemoryFileContent(path=rel, content="", truncated=truncated, binary=True, size=size)
    return MemoryFileContent(path=rel, content=text, truncated=truncated, binary=False, size=size)


__all__ = ["MAX_FILE_BYTES", "MAX_TREE_DEPTH", "build_tree", "read_file"]
