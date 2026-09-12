"""On-disk layout for the knowledge layer — the sole owner of path construction.

One root, one rule: ``~/.coffer/knowledge/<collection>/…``. A collection is a
top-level subdirectory; below it the human nests whatever they like and the
system assigns none of it any meaning (spec knowledge FR-004). The only
directory Coffer itself creates inside a collection is ``.history/``, holding
the revisions the tidy pass superseded — dot-prefixed so ripgrep skips it and
the catalogue walks past it (FR-005, FR-052).

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


def resolve(relpath: str) -> pathlib.Path:
    """Absolute path for a knowledge-root-relative path, traversal-checked.

    The guard runs on the segments *and* on the resolved result: a symlink
    inside the root could otherwise point out of it.
    """
    root = knowledge_root()
    candidate = root.joinpath(*split(relpath))
    root_resolved = root.resolve() if root.exists() else root
    if candidate.exists() and not candidate.resolve().is_relative_to(root_resolved):
        raise UnsafeKnowledgePath(relpath, "escapes the knowledge root")
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
