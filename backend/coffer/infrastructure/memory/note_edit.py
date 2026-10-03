"""A person's edit of one note's body (spec memory "Edit a memory in the web UI
or on disk").

The note file is the note: this replaces the text after the frontmatter and
keeps every frontmatter key as it stands, stamping only ``updated_at``. The
write is conditional on the fingerprint the editor's read carried — the sha256
of the file's bytes — so a note a distil pass or a person's own editor changed
since is refused with :class:`NoteConflict` and left untouched. The compare and
the write are one synchronous step, so nothing in this process lands between
them.
"""

from __future__ import annotations

import hashlib

from coffer.domain.memory.errors import NoteConflict
from coffer.infrastructure.memory import paths
from coffer.infrastructure.memory.frontmatter import (
    atomic_write,
    read_text,
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.memory.store import NoteNotFound


def fingerprint(raw: bytes) -> str:
    """sha256 hex of a note file's bytes."""
    return hashlib.sha256(raw).hexdigest()


def note_fingerprint(partition: str, slug: str) -> str:
    """The fingerprint of the note as it is on disk now."""
    path = paths.note_path(partition, slug)
    if not path.is_file():
        raise NoteNotFound(partition, slug)
    return fingerprint(path.read_bytes())


def save_body(
    partition: str, slug: str, body: str, *, expected_fingerprint: str, stamp: str
) -> str:
    """Replace the note's body; returns the new fingerprint."""
    path = paths.note_path(partition, slug)
    if not path.is_file():
        raise NoteNotFound(partition, slug)
    raw = path.read_bytes()
    current = fingerprint(raw)
    if current != expected_fingerprint:
        _frontmatter, current_body = split_frontmatter(read_text(path))
        raise NoteConflict(slug, current_body=current_body, current_fingerprint=current)
    frontmatter, _old = split_frontmatter(raw.decode("utf-8"))
    frontmatter["updated_at"] = stamp
    rendered = render_frontmatter(frontmatter, body.rstrip("\n") + "\n")
    atomic_write(path, rendered)
    return fingerprint(rendered.encode("utf-8"))


__all__ = ["fingerprint", "note_fingerprint", "save_body"]
