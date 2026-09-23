"""On-disk layout for the knowledge layer — the sole owner of path construction.

One root, one tree per collection: ``~/.coffer/knowledge/<collection>/…``.
Everything visible under a collection is a **document** — Markdown a person and
Coffer's curation pass write together, in whatever nesting either of them
chooses (spec knowledge FR-001, FR-004). The collection's ``README.md`` sits at
its root and describes it rather than being content in it (FR-007).

There is exactly one hidden directory, and it is Coffer's: ``.inbox/``, where
new material waits to be merged into the documents — an upload's extracted
text, an agent's ``coffer__write``, a migrated file. It is hidden because it is
not knowledge yet: nothing lists it, no catalogue names it, and each item is
deleted the moment a pass has folded it in (FR-005). Hidden entries are
otherwise never addressable.

``$COFFER_KNOWLEDGE_ROOT`` overrides the root for tests. Every segment that
becomes a path component goes through the traversal guard here (FR-006).
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.knowledge.errors import UnsafeKnowledgePath

README_NAME = "README.md"

#: Where material waits to be merged into a collection's documents (FR-005).
INBOX_DIR_NAME = ".inbox"

_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+$")


def knowledge_root() -> pathlib.Path:
    """The one directory the layer lives in."""
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "knowledge"


def check_segment(segment: str, relpath: str) -> None:
    """Refuse a path component that is hidden, all dots, or otherwise unsafe."""
    if not segment:
        raise UnsafeKnowledgePath(relpath, "empty path segment")
    if _DOTS_ONLY.fullmatch(segment):
        raise UnsafeKnowledgePath(relpath, "traversal segment")
    if segment.startswith("."):
        raise UnsafeKnowledgePath(relpath, "hidden entries are not addressable")
    if not _SAFE_SEGMENT.fullmatch(segment):
        raise UnsafeKnowledgePath(relpath, f"unsafe segment {segment!r}")


def split(relpath: str) -> list[str]:
    """The segments of a knowledge-root-relative path, each guarded."""
    cleaned = (relpath or "").strip().strip("/")
    if not cleaned:
        return []
    segments = [s for s in cleaned.split("/") if s]
    for segment in segments:
        check_segment(segment, relpath)
    return segments


def _anchor(candidate: pathlib.Path) -> pathlib.Path:
    """The nearest part of ``candidate`` that is already on disk.

    A symlink counts even when it dangles: it is the thing a later write would
    follow, so it is the thing whose target has to be checked.
    """
    for part in (candidate, *candidate.parents):
        if part.is_symlink() or part.exists():
            return part
    return candidate


def assert_inside_root(candidate: pathlib.Path, relpath: str) -> None:
    """Refuse a path that resolves outside the knowledge root.

    Checked on the nearest *existing* ancestor rather than on ``candidate``
    itself: a file that does not exist yet has nothing to resolve, but the
    directory it would be created in does — and a symlinked directory inside
    the root would carry the write wherever it points (FR-006).
    """
    root = knowledge_root()
    root_resolved = root.resolve()
    if not _anchor(candidate).resolve().is_relative_to(root_resolved):
        raise UnsafeKnowledgePath(relpath, "escapes the knowledge root")


def resolve(relpath: str) -> pathlib.Path:
    """Absolute path for a knowledge-root-relative path, traversal-checked.

    The guard runs on the segments *and* on the resolved result: a symlink
    inside the root — to a file, or to a directory a new file would land in —
    could otherwise point out of it.
    """
    candidate = knowledge_root().joinpath(*split(relpath))
    assert_inside_root(candidate, relpath)
    return candidate


def collection_dir(name: str) -> pathlib.Path:
    """The directory of one collection."""
    segments = split(name)
    if len(segments) != 1:
        raise UnsafeKnowledgePath(name, "a collection name is one path segment")
    return knowledge_root() / segments[0]


def collection_of(relpath: str) -> str:
    """The collection a relative path belongs to."""
    segments = split(relpath)
    if not segments:
        raise UnsafeKnowledgePath(relpath, "no collection in path")
    return segments[0]


def require_document(relpath: str) -> None:
    """Refuse a path that cannot name a document.

    A document lives *inside* a collection — never the collection itself, and
    never its ``README.md``, which describes the collection rather than being
    knowledge in it. The hidden inbox is out of reach already: ``split``
    refuses every dot-prefixed segment.
    """
    segments = split(relpath)
    if len(segments) < 2:
        raise UnsafeKnowledgePath(relpath, "a document lives inside a collection")
    if len(segments) == 2 and segments[1] == README_NAME:
        raise UnsafeKnowledgePath(relpath, "a collection's README is not a document")


def relative_of(path: pathlib.Path) -> str:
    """The knowledge-root-relative form of an absolute path."""
    root = knowledge_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def readme_path(collection: str) -> pathlib.Path:
    """A collection's own description file, at its root (FR-007)."""
    return collection_dir(collection) / README_NAME


def inbox_dir(collection: str) -> pathlib.Path:
    """Where a collection's unmerged material waits (FR-005)."""
    return collection_dir(collection) / INBOX_DIR_NAME
