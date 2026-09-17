"""On-disk layout for the knowledge layer — the sole owner of path construction.

One root, two lanes: ``~/.coffer/knowledge/<collection>/{sources,topics}/…``.
A collection is a top-level subdirectory holding both (spec knowledge FR-001);
its ``README.md`` sits between them at the collection root, belonging to
neither (FR-007).

The lanes are directories rather than a frontmatter property because what they
carry is *who may write here* — the one thing a key inside a file cannot say.
``sources/`` is written by a person, an upload and ``coffer__write``; ``topics/``
is written by the curation pass and by nothing else (FR-013, FR-021). Below a
lane the nesting is free: the person's own under ``sources/``, curation's under
``topics/`` (FR-004).

Coffer creates no hidden directory of its own. ``.history/`` and ``.raw/`` are
gone: the first existed because a topic was the only copy, which sources now
are, and the second existed to keep an uploaded original out of retrieval,
which having no retrieval surface does for free (FR-005).

``$COFFER_KNOWLEDGE_ROOT`` overrides the root for tests. Every segment that
becomes a path component goes through the traversal guard here (FR-006).
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.knowledge.errors import UnsafeKnowledgePath

SOURCES_DIR_NAME = "sources"
TOPICS_DIR_NAME = "topics"
README_NAME = "README.md"

#: The two lanes, in the order every surface presents them.
LANES = (SOURCES_DIR_NAME, TOPICS_DIR_NAME)

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


def lane_of(relpath: str) -> str | None:
    """The lane a relative path belongs to, or ``None`` for a collection root.

    ``None`` is a legitimate answer for the collection itself and for its
    ``README.md``; it is not an answer for a content file, which is why
    :func:`require_lane` exists beside this.
    """
    segments = split(relpath)
    if len(segments) < 2:
        return None
    lane = segments[1]
    return lane if lane in LANES else None


def require_lane(relpath: str, *, expected: str | None = None) -> str:
    """The lane ``relpath`` names, refusing anything outside one.

    Every content read and write resolves through here, so "a file lives in a
    lane" is a property of path construction rather than a rule each caller
    remembers. ``expected`` additionally pins which lane, which is how the
    curation pass is kept out of ``sources/`` (FR-021) and how an agent write
    is kept out of ``topics/`` (FR-013).
    """
    lane = lane_of(relpath)
    if lane is None:
        lanes = " or ".join(f"{name}/" for name in LANES)
        raise UnsafeKnowledgePath(relpath, f"a knowledge file lives under {lanes}")
    if expected is not None and lane != expected:
        raise UnsafeKnowledgePath(relpath, f"expected the {expected}/ lane, got {lane}/")
    return lane


def relative_of(path: pathlib.Path) -> str:
    """The knowledge-root-relative form of an absolute path."""
    root = knowledge_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def readme_path(collection: str) -> pathlib.Path:
    """A collection's own description file, outside both lanes (FR-007)."""
    return collection_dir(collection) / README_NAME


def lane_dir(collection: str, lane: str) -> pathlib.Path:
    """One lane's directory inside a collection."""
    if lane not in LANES:
        raise UnsafeKnowledgePath(f"{collection}/{lane}", f"unknown lane {lane!r}")
    return collection_dir(collection) / lane


def sources_dir(collection: str) -> pathlib.Path:
    """Where a collection keeps the material people contributed."""
    return lane_dir(collection, SOURCES_DIR_NAME)


def topics_dir(collection: str) -> pathlib.Path:
    """Where a collection keeps the documents curation derived."""
    return lane_dir(collection, TOPICS_DIR_NAME)


def lane_relpath(collection: str, lane: str, *rest: str) -> str:
    """A knowledge-root-relative path inside one lane, guarded segment by segment."""
    if lane not in LANES:
        raise UnsafeKnowledgePath(f"{collection}/{lane}", f"unknown lane {lane!r}")
    parts = [collection, lane, *[p for p in rest if p]]
    joined = "/".join(parts)
    split(joined)
    return joined
