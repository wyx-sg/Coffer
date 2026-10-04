"""How a new note is named, typed and stamped (spec memory "Store each note as one
Markdown file with frontmatter").

Small and pure: the distil pass and a hand deletion both need a timestamp, and the
pass needs a file name that collides with nothing in the partition.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

from coffer.domain.memory.note import NOTE_TYPES, TYPE_PROJECT

_SEPARATORS = re.compile(r"[\s_/\\]+")
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
_MAX_SLUG_CHARS = 80


def now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    stem = _DASHES.sub("-", _DROP.sub("", _SEPARATORS.sub("-", normalized))).strip("-")
    return (stem or "note")[:_MAX_SLUG_CHARS].strip("-") or "note"


def unique_slug(title: str, taken: set[str]) -> str:
    """A file name for a new note that collides with nothing in the partition.

    ``taken`` carries retired slugs too: re-using the file name of a note this
    partition retired would make ``RETIRED.md`` read as though a live note had
    been removed.
    """
    base = _slugify(title)
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def note_type(*candidates: str) -> str:
    """The first candidate that is a real note type, else ``project``.

    A type decides a note's index group and, for the personal types, which
    partition it belongs in at all, so a stray value from a hand-edited source
    file must not travel into a note.
    """
    for value in candidates:
        if value in NOTE_TYPES:
            return value
    return TYPE_PROJECT


__all__ = ["note_type", "now", "unique_slug"]
