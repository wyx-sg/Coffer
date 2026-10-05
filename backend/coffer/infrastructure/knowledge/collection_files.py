"""The two writes a collection's own files take besides its documents: its
README's description, and every file of a deleted collection put back.

A collection has no title (spec knowledge "Read a collection's description from
its README"): its heading is its folder name, and what it is about is the first
paragraph of its ``README.md``. Editing that description rewrites exactly that
paragraph and leaves the rest of the README — anything a person wrote under it —
as it was.

Restoring a deleted collection (spec knowledge "Undo a knowledge delete from its
toast") puts back, byte for byte, every file the delete
removed: its documents, its README and any inbox items.
Documents go through the same guard every document write does; the README and
an inbox item are the two non-document paths a collection holds, and each is
resolved through the module that owns its shape.
"""

from __future__ import annotations

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write, decode


def _replace_first_paragraph(body: str, description: str) -> str:
    """``body`` with its first non-heading paragraph replaced by ``description``
    (or ``description`` inserted after the leading headings when it has none)."""
    lines = body.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped and not stripped.startswith("#"):
                start = i
            continue
        if not stripped:
            end = i
            break
    new = description.strip().splitlines()
    if start is None:
        head = list(lines)
        while head and not head[-1].strip():
            head.pop()
        out = [*head, "", *new] if head else new
    else:
        out = [*lines[:start], *new, *lines[end if end is not None else len(lines) :]]
    return "\n".join(out).rstrip("\n") + "\n"


def write_description(collection: str, description: str) -> None:
    """Make ``description`` the opening paragraph of ``collection``'s README,
    creating the README (headed by the folder name) when there is none."""
    readme = paths.readme_path(collection)
    if not readme.is_file():
        atomic_write(readme, f"# {collection}\n\n{description.strip()}\n")
        return
    raw = readme.read_text(encoding="utf-8", errors="replace")
    _, body = split_frontmatter(raw)
    # Whatever precedes the body — a frontmatter fence a person added — is kept.
    head = raw[: len(raw) - len(body)] if raw.endswith(body) else ""
    atomic_write(readme, head + _replace_first_paragraph(body, description))


def restore_file(relpath: str, raw: bytes) -> None:
    """Put back one file of a deleted collection exactly as it was: a document,
    the README, or an inbox item."""
    in_inbox = paths.inbox_parts(relpath)
    if in_inbox is not None:
        collection, item = in_inbox
        if item is None:
            raise UnsafeKnowledgePath(relpath, "the inbox itself is not a file")
        target = paths.inbox_dir(collection) / item
    else:
        segments = paths.split(relpath)
        if len(segments) == 2 and segments[1] == paths.README_NAME:
            target = paths.readme_path(segments[0])
        else:
            paths.require_document(relpath)
            target = paths.resolve(relpath)
    atomic_write(target, decode(raw))


__all__ = ["restore_file", "write_description"]
