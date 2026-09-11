"""Read-only file-tree + file-content helpers for a skill's master folder.

A skill's canonical master folder lives at ``~/.coffer/skills/<name>/`` and is
Coffer-owned (see ``infrastructure/skill/master_store.py``). Surfaces show that
folder as a file tree, let the user read individual files, and let them save an
edited file back (``write_skill_file``).

This is a "helper module beside ``service.py``" (like ``verify_ops.py``):
free functions, no class state. They are pure-ish reads of
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

import hashlib
import os
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

# Chunk size for the streaming content fingerprint. Bounded so hashing a large
# file never pulls the whole thing into memory.
_HASH_CHUNK_BYTES = 64 * 1024


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
    """A single skill file's contents, plus the fingerprint that guards a write.

    ``fingerprint`` digests the file's RAW BYTES on disk, never the ``content``
    field: ``content`` is truncated past ``MAX_FILE_BYTES`` and empty for a
    binary file, so hashing it would make an oversized file's fingerprint fail
    to round-trip through an unchanged read → write. Hashing the bytes also
    means an edit past the truncation point is still detected as a conflict.
    """

    path: str
    content: str
    truncated: bool
    binary: bool
    size: int
    fingerprint: str = ""


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


def _fingerprint(path: pathlib.Path) -> str:
    """sha256 hex digest of a file's full on-disk bytes.

    Streamed in fixed chunks rather than read whole: a skill's master folder is
    capped at 50 MB in total, but one file inside it can still be far larger
    than the 256 KiB the viewer reads, and the digest must cover all of it for
    the staleness check to mean anything.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    # Hashed from the file itself, so every branch below (binary, truncated,
    # plain text) hands back a fingerprint the caller can write back with.
    fp = _fingerprint(candidate)

    if b"\x00" in chunk:
        return FileContent(
            path=rel, content="", truncated=truncated, binary=True, size=size, fingerprint=fp
        )
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        if truncated:
            # The 256 KiB cut may have split a trailing multi-byte UTF-8
            # sequence; that alone doesn't make the file binary. Decode the
            # valid prefix and drop the dangling bytes rather than mislabel a
            # large text file as binary.
            text = chunk.decode("utf-8", errors="ignore")
            return FileContent(
                path=rel, content=text, truncated=True, binary=False, size=size, fingerprint=fp
            )
        return FileContent(
            path=rel, content="", truncated=truncated, binary=True, size=size, fingerprint=fp
        )
    return FileContent(
        path=rel, content=text, truncated=truncated, binary=False, size=size, fingerprint=fp
    )


def write_skill_file(master_folder: pathlib.Path, relpath: str, content: str) -> FileContent:
    """Overwrite an existing text file under ``master_folder`` and re-read it.

    Containment is enforced exactly as in :func:`read_skill_file`: the resolved
    target MUST stay inside the (resolved) master folder. Only an *existing
    regular file* may be written — this is an editor for the skill's current
    files, not a create-file or create-directory affordance. The write is
    atomic (temp file + ``os.replace``) so a failure can't leave a half-written
    file, and it preserves the existing UTF-8 text contract: a binary file is
    rejected rather than clobbered with text. The re-read result carries the
    NEW ``fingerprint``, so an editor that keeps the buffer open can issue its
    next write without a round-trip through the read endpoint.

    This function does no staleness check of its own — the optimistic
    ``expected_fingerprint`` comparison lives one layer up, in
    ``content_ops.write_skill_file``, beside the existence check and the audit
    record, so it happens before anything here touches the filesystem.

    Raises:
        ValueError: ``relpath`` resolves outside the master folder, the content
            exceeds ``MAX_FILE_BYTES``, or the target is an existing binary file.
        FileNotFoundError: no regular file exists at the resolved path.
    """
    root = master_folder.resolve()
    candidate = (root / relpath).resolve(strict=False)
    if not is_within(candidate, root):
        raise ValueError(f"path escapes skill folder: {relpath!r}")
    if candidate == root or not candidate.is_file():
        raise FileNotFoundError(relpath)

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ValueError(f"content exceeds {MAX_FILE_BYTES} bytes")

    # Refuse to turn an existing binary file into text — the editor only ever
    # surfaces text files, so a binary target here means a malformed request.
    with candidate.open("rb") as fh:
        existing_head = fh.read(MAX_FILE_BYTES + 1)
    if b"\x00" in existing_head[:MAX_FILE_BYTES]:
        raise ValueError("refusing to overwrite a binary file with text")

    # Atomic replace: write a sibling temp file, fsync, then rename over the
    # target. The temp file lives in the same directory so os.replace is a true
    # atomic rename (same filesystem).
    tmp = candidate.with_name(f".{candidate.name}.coffer-tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, candidate)
    finally:
        # If os.replace succeeded the temp is gone; clean up only on failure.
        tmp.unlink(missing_ok=True)

    return read_skill_file(master_folder, relpath)
