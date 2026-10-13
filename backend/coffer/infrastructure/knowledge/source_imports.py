"""Which sources already hold an imported page, and marking one replaced
(spec knowledge "Import a Confluence page as a readable source with its
attachments").

A page is identified by the id its system gave it, never by its title: two
pages may share a title, and a renamed page is still the same page. The id is
read wherever a source keeps it — ``origin.page_id`` (what Coffer writes),
a top-level ``page_id`` / ``pageId``, a ``pageId=`` in its origin URL, or the
same keys in a frontmatter block left at the top of the body by an import
from before frontmatter was read (so the double-fronted sources an older
version wrote are still found, without being rewritten).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write, decode, render

#: The frontmatter key naming the source that replaces this one.
SUPERSEDED_KEY = "superseded_by"
_PAGE_IN_URL = re.compile(r"(?:pageId=|/pages/)(\d+)")


def page_id_of(meta: Mapping[str, Any]) -> str:
    """The page id ``meta`` records, or ``""``."""
    origin = meta.get("origin")
    if isinstance(origin, Mapping):
        found = page_id_of(origin)
        if found:
            return found
    for key in ("page_id", "pageId"):
        value = meta.get(key)
        if value not in (None, "") and not isinstance(value, Mapping | list | bool):
            return str(value).strip()
    for key in ("url", "origin", "source"):
        value = meta.get(key)
        if isinstance(value, str):
            match = _PAGE_IN_URL.search(value)
            if match:
                return match.group(1)
    return ""


def imported(collection: str, page_id: str) -> list[str]:
    """The sources of ``collection`` that hold page ``page_id``, as
    knowledge-root-relative paths, oldest name first. Replaced ones count:
    a page imported again replaces its newest import."""
    if not page_id:
        return []
    directory = paths.sources_dir(collection)
    if not directory.is_dir():
        return []
    found: list[str] = []
    for path in sorted(directory.rglob("*.md")):
        rel = path.relative_to(directory)
        if any(part.startswith(".") for part in rel.parts) or not path.is_file():
            continue
        fm, body = split_frontmatter(decode(path.read_bytes()))
        inner, _ = split_frontmatter(body)
        if page_id in (page_id_of(fm), page_id_of(inner)):
            found.append(paths.relative_of(path))
    return found


def current(collection: str, page_id: str) -> list[str]:
    """Of :func:`imported`, the sources not yet replaced."""
    out: list[str] = []
    for relpath in imported(collection, page_id):
        fm, _ = split_frontmatter(decode(paths.resolve(relpath).read_bytes()))
        if not fm.get(SUPERSEDED_KEY):
            out.append(relpath)
    return out


def mark_superseded(relpath: str, successor: str) -> None:
    """Record on the source at ``relpath`` that ``successor`` (a source's
    slug) replaces it. Only that key changes: the body and every other key are
    kept, so the older import stays readable and its history intact."""
    path = paths.resolve(relpath)
    fm, body = split_frontmatter(decode(path.read_bytes()))
    fm[SUPERSEDED_KEY] = successor
    atomic_write(path, render(fm, body))


__all__ = ["SUPERSEDED_KEY", "current", "imported", "mark_superseded", "page_id_of"]
