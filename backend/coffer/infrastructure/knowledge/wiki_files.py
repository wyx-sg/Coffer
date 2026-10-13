"""A collection's Markdown read off disk, ready for ``wiki.build`` to join into
a graph (spec knowledge "Link pages by slug and check every link", "Check a
collection mechanically on every read").

Pages are the Markdown under ``pages/``, sources the Markdown under
``sources/``. Every other visible Markdown file — the README, a root
``index.md``, ``log.md`` or ``schema.md``, a file in a folder a person made —
is a :class:`Note`, and so is each source: its links count towards the orphan
check and are checked themselves (a source's are not: it is kept as it came, so
nothing could fix them), but it is never checked as a page.
``assets/`` holds link targets only, so nothing in it is read.

The README's frontmatter sets the collection's rules: ``verify_after_days``
(how long a ``verified`` date holds) and ``sourceless_types`` (page types that
need no ``sources`` or ``evidence``). A page's own ``verify_after_days``
overrides the collection's.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.wiki_links import links_in, markdown_links_in

#: The keys the guide lets an agent add to a source: ``ingest: skipped``, the
#: newer source that replaces it, and a short summary of what it says (ADR
#: knowledge-stays-current-through-flags-coffer-computes).
INGEST_KEY = "ingest"
INGEST_SKIPPED = "skipped"
SUPERSEDED_KEY = "superseded_by"
SUMMARY_KEY = "summary"

#: The README frontmatter key that sets how many days a page's ``verified``
#: date holds, and its default; ``0`` turns the check off.
VERIFY_KEY = "verify_after_days"
DEFAULT_VERIFY_DAYS = 90

#: The README frontmatter key naming page types that need no ``sources`` or
#: ``evidence``; the page key that stands in for ``sources``.
SOURCELESS_KEY = "sourceless_types"
EVIDENCE_KEY = "evidence"

#: Keys a page must carry to be complete.
_REQUIRED_PAGE_KEYS = ("title", "type", "description")


def _as_list(value: object) -> tuple[str, ...]:
    """A frontmatter list that a writer may have given as one string."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    if isinstance(value, Iterable):
        return tuple(str(v).strip() for v in value if v is not None and str(v).strip())
    return (str(value),)


@dataclass(frozen=True)
class Page:
    path: str
    slug: str
    title: str
    page_type: str
    description: str
    sources: tuple[str, ...]
    aliases: tuple[str, ...]
    links: tuple[str, ...]
    missing_keys: tuple[str, ...]
    #: When the page was last checked against its sources or the code.
    verified: str = ""
    #: Standard link and image targets that name a path, as written.
    doc_links: tuple[str, ...] = ()
    #: Free-form ``evidence`` entries; Coffer does not interpret them.
    evidence: tuple[str, ...] = ()
    #: The page's own ``verify_after_days``; ``None`` keeps the collection's.
    verify_after_days: int | None = None


@dataclass(frozen=True)
class Note:
    """A Markdown file of the collection that is not a page — a source, the
    README, a root index or log, a file in a folder a person made. Its links
    count, and are checked unless it is a source; it is never checked as a
    page."""

    path: str
    links: tuple[str, ...] = ()
    doc_links: tuple[str, ...] = ()
    #: Whether its own dead, ambiguous or outside links are findings. A
    #: source is kept as it came and never edited, so its links only count.
    checked: bool = True


@dataclass(frozen=True)
class Source:
    path: str
    slug: str
    title: str
    skipped: bool
    #: The slug of the newer source that replaces this one; empty when none.
    superseded_by: str = ""
    summary: str = ""


def _interval(value: object) -> int | None:
    """A ``verify_after_days`` value as whole non-negative days; ``None`` when
    it is missing or unreadable."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        days = int(value)
    except ValueError:
        return None
    return days if days >= 0 else None


def _readme_front(collection: str) -> dict[str, Any]:
    readme = paths.readme_path(collection)
    return _read(readme)[0] if readme.is_file() else {}


def verify_days(collection: str) -> int:
    """The collection's ``verify_after_days`` from its README frontmatter, or
    :data:`DEFAULT_VERIFY_DAYS` when it sets none or an unreadable one."""
    days = _interval(_readme_front(collection).get(VERIFY_KEY))
    return DEFAULT_VERIFY_DAYS if days is None else days


def _markdown_under(directory: pathlib.Path, *, skip: Iterable[str] = ()) -> list[pathlib.Path]:
    """Every visible Markdown file under ``directory``; ``skip`` names
    top-level folders left out."""
    if not directory.is_dir():
        return []
    skipped = set(skip)
    found: list[pathlib.Path] = []
    for root, dirnames, filenames in os.walk(directory):
        top = pathlib.Path(root) == directory
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and not (top and d in skipped)
        )
        found += [
            pathlib.Path(root) / f
            for f in sorted(filenames)
            if f.endswith(".md") and not f.startswith(".")
        ]
    return found


def _read(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    return split_frontmatter(text.replace("\r\n", "\n"))


def _note(path: pathlib.Path, body: str, *, checked: bool = True) -> Note:
    return Note(paths.relative_of(path), links_in(body), markdown_links_in(body), checked)


@dataclass
class CollectionFiles:
    """What :func:`read` found: the files, and the README's rules."""

    pages: list[Page] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    verify_after_days: int = DEFAULT_VERIFY_DAYS
    sourceless_types: frozenset[str] = frozenset()


def _page(path: pathlib.Path, fm: dict[str, Any], body: str) -> Page:
    return Page(
        path=paths.relative_of(path),
        slug=path.stem,
        title=str(fm.get("title") or path.stem),
        page_type=str(fm.get("type") or "").strip(),
        description=str(fm.get("description") or ""),
        sources=_as_list(fm.get("sources")),
        aliases=_as_list(fm.get("aliases")),
        links=links_in(body),
        missing_keys=tuple(k for k in _REQUIRED_PAGE_KEYS if not str(fm.get(k) or "").strip()),
        verified=str(fm.get("verified") or "").strip(),
        doc_links=markdown_links_in(body),
        evidence=_as_list(fm.get(EVIDENCE_KEY)),
        verify_after_days=_interval(fm.get(VERIFY_KEY)),
    )


def _source(path: pathlib.Path, fm: dict[str, Any]) -> Source:
    return Source(
        path=paths.relative_of(path),
        slug=path.stem,
        title=str(fm.get("title") or path.stem),
        skipped=str(fm.get(INGEST_KEY) or "").strip().lower() == INGEST_SKIPPED,
        superseded_by=str(fm.get(SUPERSEDED_KEY) or "").strip(),
        summary=" ".join(str(fm.get(SUMMARY_KEY) or "").split()),
    )


def read(collection: str) -> CollectionFiles:
    """Every page, source and note of ``collection``, and its README's rules."""
    readme = _readme_front(collection)
    days = _interval(readme.get(VERIFY_KEY))
    files = CollectionFiles(
        verify_after_days=DEFAULT_VERIFY_DAYS if days is None else days,
        sourceless_types=frozenset(t.lower() for t in _as_list(readme.get(SOURCELESS_KEY))),
    )
    for path in _markdown_under(paths.sources_dir(collection)):
        fm, body = _read(path)
        files.sources.append(_source(path, fm))
        files.notes.append(_note(path, body, checked=False))
    for path in _markdown_under(paths.pages_dir(collection)):
        fm, body = _read(path)
        files.pages.append(_page(path, fm, body))
    keep = (paths.PAGES_DIR_NAME, paths.SOURCES_DIR_NAME, paths.ASSETS_DIR_NAME)
    for path in _markdown_under(paths.collection_dir(collection), skip=keep):
        files.notes.append(_note(path, _read(path)[1]))
    return files


__all__ = [
    "DEFAULT_VERIFY_DAYS",
    "EVIDENCE_KEY",
    "INGEST_KEY",
    "INGEST_SKIPPED",
    "SOURCELESS_KEY",
    "SUMMARY_KEY",
    "SUPERSEDED_KEY",
    "VERIFY_KEY",
    "CollectionFiles",
    "Note",
    "Page",
    "Source",
    "read",
    "verify_days",
]
