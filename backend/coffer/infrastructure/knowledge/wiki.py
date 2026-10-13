"""One collection read as a wiki: its pages, its sources, the other Markdown
files that sit beside them, and how they refer to each other (spec knowledge
"Link pages by slug or relative path and check every link", "Derive which
sources wait from the pages that cite them", "Check a collection mechanically
on every read").

:func:`build` walks a collection once and returns a :class:`WikiGraph`, with
the rules its README sets (``wiki_rules``). A Markdown file outside ``pages/``,
``sources/`` and ``assets/`` — the README, an ``index.md``, a ``log.md``, a note
in a folder of the person's own — is a **note**: it is not a page, so nothing
asks it for a type, sources or a recheck, but its links are checked and a page
it links to is not an orphan, so a root index is how a collection navigates. Nothing is
stored: every read builds it again from the files, so it cannot disagree with
them (spec knowledge "Store each collection as one tree of Markdown files").
A collection is hundreds of files at most, so
one walk is cheap.

A page's slug is its file stem, and a link names a slug or one of a page's
``aliases``. A ``sources`` entry names a source's slug. Matching ignores case
and Unicode width, the way file names are normalised (``naming.slugify``), and
tolerates a trailing ``.md`` or a leading folder, so a link written as a path
still resolves — the guide asks for slugs, but a reader should not be punished
for a near miss.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.knowledge.entry import Finding
from coffer.infrastructure.knowledge import links as link_forms
from coffer.infrastructure.knowledge import paths, wiki_findings, wiki_rules
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.wiki_findings import (
    AMBIGUOUS_LINK,
    DEAD_LINK,
    DUPLICATE_SLUG,
    FINDING_KINDS,
    INCOMPLETE_PAGE,
    MISSING_SOURCE,
    ORPHAN_PAGE,
    OUTSIDE_LINK,
    OVERVIEW_TYPE,
    STALE_PAGE,
    SUPERSEDED_SOURCE,
    UNSOURCED_PAGE,
    WAITING_SOURCE,
)
from coffer.infrastructure.knowledge.wiki_rules import (
    DEFAULT_VERIFY_DAYS,
    VERIFY_KEY,
    as_list,
)

#: The keys the guide lets an agent add to a source: ``ingest: skipped``, the
#: newer source that replaces it, and a short summary of what it says (ADR
#: knowledge-stays-current-through-flags-coffer-computes).
INGEST_KEY = "ingest"
INGEST_SKIPPED = "skipped"
SUPERSEDED_KEY = "superseded_by"
SUMMARY_KEY = "summary"

#: What a page lists, beside or instead of ``sources``, as the evidence it was
#: checked against: code it read, a config, an observation (``wiki_rules``).
EVIDENCE_KEY = "evidence"

#: Keys a page must carry to be complete.
_REQUIRED_PAGE_KEYS = ("title", "type", "description")


def normalise(name: str) -> str:
    """A slug, an alias or a link target in the form they are matched in."""
    text = unicodedata.normalize("NFKC", name or "").strip()
    text = text.rsplit("/", 1)[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text.strip().lower()


def links_in(body: str) -> tuple[str, ...]:
    """Every ``[[target]]`` and ``[[target|text]]`` target outside code, in order."""
    return link_forms.wiki_links(body)


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
    #: Standard Markdown links to files, as written relative to the page.
    path_links: tuple[str, ...] = ()
    #: What else the page was checked against: code, a config, an observation.
    evidence: tuple[str, ...] = ()
    #: The page's own recheck interval, ``None`` to follow the collection's.
    verify_after_days: int | None = None


@dataclass(frozen=True)
class Note:
    """A Markdown file that is neither a page nor a source: the README, an
    index, a log, a note in a folder of the person's own. Only its links count."""

    path: str
    links: tuple[str, ...]
    path_links: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    path: str
    slug: str
    title: str
    skipped: bool
    #: The slug of the newer source that replaces this one; empty when none.
    superseded_by: str = ""
    summary: str = ""


@dataclass
class WikiGraph:
    """A collection's pages and sources and the names they answer to."""

    pages: list[Page] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    #: Normalised page slug or alias → the pages it names.
    names: dict[str, set[str]] = field(default_factory=dict)
    #: Normalised source slug → the sources it names.
    source_names: dict[str, set[str]] = field(default_factory=dict)
    #: How many days a page's ``verified`` date holds; ``0`` turns it off.
    verify_after_days: int = DEFAULT_VERIFY_DAYS
    #: Page types not asked for ``sources`` (lower-cased).
    types_without_sources: tuple[str, ...] = wiki_rules.DEFAULT_SOURCELESS_TYPES
    #: The day staleness is measured on.
    today: dt.date = field(default_factory=dt.date.today)

    def resolve(self, target: str) -> list[str]:
        """The files a link target names, in path order: the pages it names,
        else the sources — a page and the source it was compiled from often
        share a slug, and the link means the page."""
        key = normalise(target)
        return sorted(self.names.get(key) or self.source_names.get(key) or ())

    def resolve_source(self, slug: str) -> list[str]:
        return sorted(self.source_names.get(normalise(slug), ()))

    def page(self, path: str) -> Page | None:
        return next((p for p in self.pages if p.path == path), None)

    def source(self, path: str) -> Source | None:
        return next((s for s in self.sources if s.path == path), None)

    def citing(self, source_path: str) -> list[Page]:
        """The pages whose ``sources`` name ``source_path``."""
        return [
            p for p in self.pages if any(source_path in self.resolve_source(s) for s in p.sources)
        ]

    def cited(self) -> set[str]:
        return {path for p in self.pages for s in p.sources for path in self.resolve_source(s)}

    def waiting(self) -> list[Source]:
        """Sources no page cites, none marks skipped and none superseded."""
        cited = self.cited()
        return [
            s for s in self.sources if s.path not in cited and not s.skipped and not s.superseded_by
        ]

    def successor(self, source: Source) -> str | None:
        """The source that replaces ``source``, when its ``superseded_by``
        names exactly one."""
        if not source.superseded_by:
            return None
        hits = self.resolve_source(source.superseded_by)
        return hits[0] if len(hits) == 1 else None

    def successors(self, source: Source) -> list[str]:
        """Every source after ``source`` in its chain of replacements, nearest
        first; a cycle stops where it repeats."""
        chain: list[str] = []
        current: Source | None = source
        while current is not None:
            nxt = self.successor(current)
            if nxt is None or nxt == source.path or nxt in chain:
                break
            chain.append(nxt)
            current = self.source(nxt)
        return chain

    def is_stale(self, page: Page) -> bool:
        """Whether ``page`` is due a recheck: its ``verified`` date is missing,
        unreadable or older than :attr:`verify_after_days`."""
        interval = (
            self.verify_after_days if page.verify_after_days is None else page.verify_after_days
        )
        if interval <= 0:
            return False
        checked = parse_day(page.verified)
        return checked is None or (self.today - checked).days > interval

    def unsourced(self, page: Page) -> bool:
        """Whether ``page`` makes claims with nothing named to check them by: no
        ``sources``, no ``evidence``, and a type the collection asks sources of."""
        if page.sources or page.evidence:
            return False
        return page.page_type.lower() not in self.types_without_sources

    def follow(self, from_path: str, target: str) -> tuple[str | None, bool]:
        """Where a relative link written in ``from_path`` leads, and whether a
        file or folder is there. ``(None, False)`` for one that leaves the
        knowledge root; a hidden entry is never there."""
        resolved = link_forms.resolve_path(from_path, target)
        if resolved is None:
            return None, False
        if any(part.startswith(".") for part in resolved.split("/")):
            return resolved, False
        return resolved, (paths.knowledge_root() / resolved).exists()

    def findings(self) -> list[Finding]:
        """Every mechanical finding, grouped by kind in :data:`FINDING_KINDS` order."""
        return wiki_findings.compute(self)


def parse_day(value: object) -> dt.date | None:
    """A ``YYYY-MM-DD`` date (a full timestamp is read by its date); ``None``
    when it is missing or not a date."""
    text = str(value or "").strip()[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def verify_days(collection: str) -> int:
    """The collection's ``verify_after_days`` from its README frontmatter, or
    :data:`DEFAULT_VERIFY_DAYS` when it sets none or an unreadable one."""
    return wiki_rules.read(collection).verify_after_days


def _markdown_under(
    directory: pathlib.Path, *, skip: frozenset[str] = frozenset()
) -> list[pathlib.Path]:
    """Markdown files under ``directory``; ``skip`` names folders at its top
    level to leave out."""
    if not directory.is_dir():
        return []
    found: list[pathlib.Path] = []
    for root, dirnames, filenames in os.walk(directory):
        top = pathlib.Path(root) == directory
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and not (top and d in skip)
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


def build(collection: str, *, today: dt.date | None = None) -> WikiGraph:
    """Read a collection's pages and sources into a :class:`WikiGraph`."""
    rules = wiki_rules.read(collection)
    graph = WikiGraph(
        verify_after_days=rules.verify_after_days,
        types_without_sources=rules.types_without_sources,
    )
    if today is not None:
        graph.today = today
    for path in _markdown_under(paths.sources_dir(collection)):
        fm, _ = _read(path)
        source = Source(
            path=paths.relative_of(path),
            slug=path.stem,
            title=str(fm.get("title") or path.stem),
            skipped=str(fm.get(INGEST_KEY) or "").strip().lower() == INGEST_SKIPPED,
            superseded_by=str(fm.get(SUPERSEDED_KEY) or "").strip(),
            summary=" ".join(str(fm.get(SUMMARY_KEY) or "").split()),
        )
        graph.sources.append(source)
        graph.source_names.setdefault(normalise(path.stem), set()).add(source.path)
    for path in _markdown_under(paths.pages_dir(collection)):
        fm, body = _read(path)
        page = Page(
            path=paths.relative_of(path),
            slug=path.stem,
            title=str(fm.get("title") or path.stem),
            page_type=str(fm.get("type") or "").strip(),
            description=str(fm.get("description") or ""),
            sources=as_list(fm.get("sources")),
            aliases=as_list(fm.get("aliases")),
            links=links_in(body),
            missing_keys=tuple(k for k in _REQUIRED_PAGE_KEYS if not str(fm.get(k) or "").strip()),
            verified=str(fm.get("verified") or "").strip(),
            path_links=link_forms.path_links(body),
            evidence=as_list(fm.get(EVIDENCE_KEY)),
            verify_after_days=wiki_rules.days(fm),
        )
        graph.pages.append(page)
        for name in (page.slug, *page.aliases):
            graph.names.setdefault(normalise(name), set()).add(page.path)
    skip = frozenset({paths.PAGES_DIR_NAME, paths.SOURCES_DIR_NAME, paths.ASSETS_DIR_NAME})
    for path in _markdown_under(paths.collection_dir(collection), skip=skip):
        _, body = _read(path)
        graph.notes.append(
            Note(
                path=paths.relative_of(path),
                links=links_in(body),
                path_links=link_forms.path_links(body),
            )
        )
    return graph


__all__ = [
    "AMBIGUOUS_LINK",
    "DEAD_LINK",
    "DEFAULT_VERIFY_DAYS",
    "DUPLICATE_SLUG",
    "EVIDENCE_KEY",
    "FINDING_KINDS",
    "INCOMPLETE_PAGE",
    "INGEST_KEY",
    "INGEST_SKIPPED",
    "MISSING_SOURCE",
    "ORPHAN_PAGE",
    "OUTSIDE_LINK",
    "OVERVIEW_TYPE",
    "STALE_PAGE",
    "SUMMARY_KEY",
    "SUPERSEDED_KEY",
    "SUPERSEDED_SOURCE",
    "UNSOURCED_PAGE",
    "VERIFY_KEY",
    "WAITING_SOURCE",
    "Note",
    "Page",
    "Source",
    "WikiGraph",
    "build",
    "links_in",
    "normalise",
    "parse_day",
    "verify_days",
]
