"""One collection read as a wiki: its pages, its sources and how they refer to
each other (spec knowledge "Link pages by slug and check every link", "Derive
which sources wait from the pages that cite them", "Check a collection
mechanically on every read").

:func:`build` walks a collection's Markdown once and returns a
:class:`WikiGraph`, with the README's ``verify_after_days`` and
``sourceless_types``. Pages are the Markdown under ``pages/``; every other
Markdown file — a source, the README, a root ``index.md`` or ``log.md``, a
folder a person made — is a :class:`Note`: its links count towards the orphan
check and are checked themselves, but it is never checked as a page. Nothing is
stored: every read builds it again from the files, so it cannot disagree with
them (spec knowledge "Store each collection as one tree of Markdown files").
A collection is hundreds of files at most, so
one walk is cheap.

A page's slug is its file stem, and a link names a slug or one of a page's
``aliases``. A ``sources`` entry names a source's slug. Matching ignores case
and Unicode width, the way file names are normalised (``naming.slugify``), and
tolerates a trailing ``.md`` or a leading folder, so a link written as a path
still resolves — the guide asks for slugs, but a reader should not be punished
for a near miss. A standard Markdown link names a path instead, relative to
the file that holds it (``wiki_links.resolve``).
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from dataclasses import dataclass, field

from coffer.domain.knowledge.entry import Finding
from coffer.infrastructure.knowledge import wiki_files, wiki_links
from coffer.infrastructure.knowledge.wiki_files import (
    DEFAULT_VERIFY_DAYS,
    EVIDENCE_KEY,
    INGEST_KEY,
    INGEST_SKIPPED,
    SOURCELESS_KEY,
    SUMMARY_KEY,
    SUPERSEDED_KEY,
    VERIFY_KEY,
    Note,
    Page,
    Source,
    verify_days,
)
from coffer.infrastructure.knowledge.wiki_links import links_in

#: Finding kinds, in the order a surface lists them.
DEAD_LINK = "dead_link"
AMBIGUOUS_LINK = "ambiguous_link"
OUTSIDE_LINK = "outside_link"
DUPLICATE_SLUG = "duplicate_slug"
MISSING_SOURCE = "missing_source"
SUPERSEDED_SOURCE = "superseded_source"
INCOMPLETE_PAGE = "incomplete_page"
UNSOURCED_PAGE = "unsourced_page"
STALE_PAGE = "stale_page"
ORPHAN_PAGE = "orphan_page"
WAITING_SOURCE = "waiting_source"
FINDING_KINDS = (
    DEAD_LINK,
    AMBIGUOUS_LINK,
    OUTSIDE_LINK,
    DUPLICATE_SLUG,
    MISSING_SOURCE,
    SUPERSEDED_SOURCE,
    INCOMPLETE_PAGE,
    UNSOURCED_PAGE,
    STALE_PAGE,
    ORPHAN_PAGE,
    WAITING_SOURCE,
)

#: The page type exempt from the orphan check: an overview is an entry point.
OVERVIEW_TYPE = "overview"


def normalise(name: str) -> str:
    """A slug, an alias or a link target in the form they are matched in."""
    text = unicodedata.normalize("NFKC", name or "").strip()
    text = text.rsplit("/", 1)[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text.strip().lower()


@dataclass
class WikiGraph:
    """A collection's pages and sources and the names they answer to."""

    pages: list[Page] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    #: Normalised page slug or alias → the pages it names.
    names: dict[str, set[str]] = field(default_factory=dict)
    #: Normalised source slug → the sources it names.
    source_names: dict[str, set[str]] = field(default_factory=dict)
    #: Every Markdown file that is not a page, sources included.
    notes: list[Note] = field(default_factory=list)
    #: How many days a page's ``verified`` date holds; ``0`` turns it off.
    verify_after_days: int = DEFAULT_VERIFY_DAYS
    #: Lower-cased page types exempt from ``unsourced_page``.
    sourceless_types: frozenset[str] = frozenset()
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
        unreadable or older than the page's own ``verify_after_days``, else
        the collection's :attr:`verify_after_days`."""
        days = self.verify_after_days if page.verify_after_days is None else page.verify_after_days
        if days <= 0:
            return False
        checked = parse_day(page.verified)
        return checked is None or (self.today - checked).days > days

    def needs_source(self, page: Page) -> bool:
        """Whether ``page`` cites nothing: no ``sources``, no ``evidence``, and
        its type is not one the README names in ``sourceless_types``."""
        if page.sources or page.evidence:
            return False
        return page.page_type.strip().lower() not in self.sourceless_types

    def _check_links(
        self, holder: str, links: tuple[str, ...], doc_links: tuple[str, ...]
    ) -> tuple[list[Finding], list[str]]:
        """The link findings of the file at ``holder`` and the files its links
        lead to, the way an orphan check counts them."""
        found: list[Finding] = []
        reached: list[str] = []
        for target in links:
            hits = self.resolve(target)
            if not hits:
                found.append(Finding(DEAD_LINK, holder, target))
            elif len(hits) > 1:
                found.append(Finding(AMBIGUOUS_LINK, holder, target, tuple(hits)))
            else:
                reached.append(hits[0])
        for target in doc_links:
            hit = wiki_links.resolve(holder, target)
            if hit.outside:
                found.append(Finding(OUTSIDE_LINK, holder, target))
            elif hit.path is None:
                found.append(Finding(DEAD_LINK, holder, target))
            else:
                reached.append(hit.path)
        return found, reached

    def findings(self) -> list[Finding]:
        """Every mechanical finding, grouped by kind in :data:`FINDING_KINDS` order."""
        found: list[Finding] = []
        page_paths = {p.path for p in self.pages}
        inbound: dict[str, int] = {p.path: 0 for p in self.pages}
        holders: list[Page | Note] = [*self.pages, *self.notes]
        for holder in holders:
            link_findings, reached = self._check_links(holder.path, holder.links, holder.doc_links)
            if not isinstance(holder, Note) or holder.checked:
                found += link_findings
            for hit in reached:
                if hit in page_paths and hit != holder.path:
                    inbound[hit] += 1
        for page in self.pages:
            cited = {path for slug in page.sources for path in self.resolve_source(slug)}
            for slug in page.sources:
                hits = self.resolve_source(slug)
                if not hits:
                    found.append(Finding(MISSING_SOURCE, page.path, slug))
                    continue
                old = self.source(hits[0])
                if old is None or not old.superseded_by:
                    continue
                later = self.successors(old)
                if later and not cited & set(later):
                    found.append(Finding(SUPERSEDED_SOURCE, page.path, slug, (later[-1],)))
            if page.missing_keys:
                found.append(Finding(INCOMPLETE_PAGE, page.path, ", ".join(page.missing_keys)))
            if self.needs_source(page):
                found.append(Finding(UNSOURCED_PAGE, page.path))
            if self.is_stale(page):
                found.append(Finding(STALE_PAGE, page.path, page.verified or None))
        for source in self.sources:
            if source.superseded_by and not self.resolve_source(source.superseded_by):
                found.append(Finding(MISSING_SOURCE, source.path, source.superseded_by))
        seen: set[tuple[str, ...]] = set()
        for alias, named in sorted(self.names.items()):
            pages_named = sorted(h for h in named if h in page_paths)
            if len(pages_named) > 1 and tuple(pages_named) not in seen:
                seen.add(tuple(pages_named))
                found.append(Finding(DUPLICATE_SLUG, pages_named[0], alias, tuple(pages_named[1:])))
        if len(self.pages) > 1:
            for page in self.pages:
                if inbound[page.path] == 0 and page.page_type.lower() != OVERVIEW_TYPE:
                    found.append(Finding(ORPHAN_PAGE, page.path))
        for source in self.waiting():
            found.append(Finding(WAITING_SOURCE, source.path))
        order = {kind: i for i, kind in enumerate(FINDING_KINDS)}
        return sorted(found, key=lambda f: (order[f.kind], f.path, f.target or ""))


def parse_day(value: object) -> dt.date | None:
    """A ``YYYY-MM-DD`` date (a full timestamp is read by its date); ``None``
    when it is missing or not a date."""
    text = str(value or "").strip()[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def build(collection: str, *, today: dt.date | None = None) -> WikiGraph:
    """Read a collection's pages, sources and other Markdown into a :class:`WikiGraph`."""
    files = wiki_files.read(collection)
    graph = WikiGraph(
        pages=files.pages,
        sources=files.sources,
        notes=files.notes,
        verify_after_days=files.verify_after_days,
        sourceless_types=files.sourceless_types,
    )
    if today is not None:
        graph.today = today
    for source in graph.sources:
        graph.source_names.setdefault(normalise(source.slug), set()).add(source.path)
    for page in graph.pages:
        for name in (page.slug, *page.aliases):
            graph.names.setdefault(normalise(name), set()).add(page.path)
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
    "SOURCELESS_KEY",
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
