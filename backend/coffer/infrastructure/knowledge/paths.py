"""On-disk layout for the knowledge layer — the sole owner of path construction.

One root, one rule: ``~/.coffer/knowledge/<collection>/…``. A collection is a
top-level subdirectory; below it the human nests whatever they like and the
system assigns none of it any meaning (spec knowledge FR-004). The only
directories Coffer itself creates inside a collection are ``.history/``,
holding the revisions the tidy pass superseded, and ``.raw/``, holding the
original bytes behind an uploaded document — both dot-prefixed so ripgrep
skips them and the catalogue walks past them (FR-005, FR-035, FR-052).

``$COFFER_KNOWLEDGE_ROOT`` overrides the root for tests. Every segment that
becomes a path component goes through the traversal guard here (FR-006).
"""

from __future__ import annotations

import os
import pathlib
import re
from datetime import UTC, datetime

from coffer.domain.knowledge.errors import UnsafeKnowledgePath

HISTORY_DIR_NAME = ".history"
RAW_DIR_NAME = ".raw"
README_NAME = "README.md"

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


def relative_of(path: pathlib.Path) -> str:
    """The knowledge-root-relative form of an absolute path."""
    root = knowledge_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def readme_path(collection: str) -> pathlib.Path:
    return collection_dir(collection) / README_NAME


def history_dir(collection: str) -> pathlib.Path:
    """Where a collection keeps the revisions tidy replaced."""
    return collection_dir(collection) / HISTORY_DIR_NAME


def history_path(relpath: str, *, now: datetime | None = None) -> pathlib.Path:
    """Archive destination for the current contents of ``relpath``.

    The file's position inside the collection is flattened into the archived
    name, so two same-named files in different folders never collide and the
    original location stays readable to whoever goes looking.
    """
    segments = split(relpath)
    if len(segments) < 2:
        raise UnsafeKnowledgePath(relpath, "not a file inside a collection")
    collection, rest = segments[0], segments[1:]
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%f")
    flattened = "__".join(rest)
    if flattened.endswith(".md"):
        flattened = flattened[: -len(".md")]
    return history_dir(collection) / f"{flattened}.{stamp}.md"


def raw_dir(collection: str) -> pathlib.Path:
    """Where a collection keeps the untouched bytes behind its converted files."""
    return collection_dir(collection) / RAW_DIR_NAME


def raw_path(relpath: str, original_name: str) -> pathlib.Path:
    """Where the original upload behind the converted file at ``relpath`` lives.

    Unlike ``history_path``, which flattens a nested path into one archived
    name (multiple old revisions of the same file must never collide), this
    *mirrors* the converted file's own directory structure: there is exactly
    one original per converted file, so nesting it the same way keeps the two
    trees walkable side by side and needs no collision-avoiding flattening.
    The converted file's own extension (``.md``) is replaced with the
    original's own extension (FR-035) — the original is a ``.pdf`` or
    ``.docx``, not a Markdown file.
    """
    segments = split(relpath)
    if len(segments) < 2:
        raise UnsafeKnowledgePath(relpath, "not a file inside a collection")
    collection, rest = segments[0], segments[1:]
    *dirs, name = rest
    stem = pathlib.Path(name).stem
    ext = pathlib.Path(original_name).suffix
    return raw_dir(collection).joinpath(*dirs, f"{stem}{ext}")
