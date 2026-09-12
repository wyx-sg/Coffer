"""File naming — the path is the identity (spec knowledge FR-002).

With no index mapping an id to a title, a file name is what a human reads in
their file manager and what an agent reads in a grep result. So names are
slugs derived from the title, not opaque ids.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata

_SEPARATORS = re.compile(r"[\s_/\\]+")
#: Keep CJK: transliterating it would produce a name neither party recognises.
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
MAX_SLUG_CHARS = 80


def slugify(title: str) -> str:
    """A readable, path-safe stem for a title. Never empty."""
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    stem = _DASHES.sub("-", _DROP.sub("", _SEPARATORS.sub("-", normalized))).strip("-")
    return (stem or "untitled")[:MAX_SLUG_CHARS].strip("-") or "untitled"


def unique_name(directory: pathlib.Path, slug: str) -> str:
    """``<slug>.md``, suffixed only when that name is already taken."""
    if not (directory / f"{slug}.md").exists():
        return f"{slug}.md"
    for n in range(2, 1000):
        candidate = f"{slug}-{n}.md"
        if not (directory / candidate).exists():
            return candidate
    raise ValueError(f"cannot find a free name for {slug!r}")
