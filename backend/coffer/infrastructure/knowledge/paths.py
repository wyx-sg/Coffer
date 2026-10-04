"""On-disk layout for the knowledge layer — the sole owner of path construction.

One root, one tree per collection: ``~/.coffer/vault/knowledge/<collection>/…``
— inside the vault repository (ADR storage-is-five-classes-by-nature), so a
collection's history is the vault's history under ``knowledge/``.
Everything visible under a collection is a **document** — Markdown a person and
Coffer and its agents write together, in whatever nesting either of them
chooses (spec knowledge "Store each collection as one tree of Markdown files",
"Allow nesting without giving it meaning"). The collection's ``README.md``
sits at its root and describes it rather than being content in it (see "Keep
the collection README out of the corpus").

There is exactly one hidden directory, and it is Coffer's: ``.inbox/``, the drop
zone where material lands before it is a document — an upload's extracted
text, a file an agent wrote there. It is hidden because it is not knowledge
yet: no count, listing or catalogue names it, and the next sweep promotes each
item into a document (see "Hide dot-prefixed entries except the inbox").
:func:`resolve` and :func:`require_document` refuse every hidden segment, so no
read, write or delete reaches the inbox through them. The one exception is
:func:`inbox_parts`, which lets a restore put back an inbox file a deleted
collection held. Every other hidden entry is never addressable.

There is no override: the root is resolved from ``HOME`` at every call, and a
tree outside the vault would be a tree its history cannot see. Every segment
that becomes a path component goes through the traversal guard here (see
"Guard every path through one module").
"""

from __future__ import annotations

import pathlib
import re

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.vault.home import vault_root

README_NAME = "README.md"

#: The knowledge root's path inside the vault repository.
VAULT_PREFIX = "knowledge"

#: Where material lands before it is promoted into a collection's documents.
INBOX_DIR_NAME = ".inbox"

_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+$")


def knowledge_root() -> pathlib.Path:
    """The one directory the layer lives in: ``vault/knowledge``."""
    return vault_root() / VAULT_PREFIX


def vault_path(relpath: str) -> str:
    """A knowledge-root-relative path as the vault repository names it."""
    cleaned = relpath.strip("/")
    return f"{VAULT_PREFIX}/{cleaned}" if cleaned else VAULT_PREFIX


def from_vault_path(path: str) -> str | None:
    """The knowledge-root-relative form of a vault path, ``None`` outside it."""
    head = f"{VAULT_PREFIX}/"
    return path[len(head) :] if path.startswith(head) else None


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
    the root would carry the write wherever it points.
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
    """A collection's own description file, at its root."""
    return collection_dir(collection) / README_NAME


def inbox_dir(collection: str) -> pathlib.Path:
    """Where a collection's unpromoted material lands."""
    return collection_dir(collection) / INBOX_DIR_NAME


def inbox_parts(relpath: str) -> tuple[str, str | None] | None:
    """``(collection, item)`` when ``relpath`` names a collection's inbox, else ``None``.

    ``<collection>/.inbox`` gives ``item`` ``None``; ``<collection>/.inbox/<name>``
    gives the item's file name. Only a restore addresses this path: the other
    segments go through the same guard as any path, and the inbox holds no
    folders, so anything deeper is refused.
    """
    cleaned = (relpath or "").strip().strip("/")
    segments = [s for s in cleaned.split("/") if s]
    if len(segments) < 2 or segments[1] != INBOX_DIR_NAME:
        return None
    if len(segments) > 3:
        raise UnsafeKnowledgePath(relpath, "the inbox holds no folders")
    check_segment(segments[0], relpath)
    if len(segments) == 2:
        return segments[0], None
    check_segment(segments[2], relpath)
    return segments[0], segments[2]
