"""The mechanical check of a collection read as a wiki (spec knowledge "Check
a collection mechanically on every read"): every finding its files give,
computed from a :class:`~coffer.infrastructure.knowledge.wiki.WikiGraph` on
every read and kept nowhere.

A link is checked wherever it is written — in a page or in a note beside the
pages, an index or a log — and a page any of them reaches is not an orphan.
Only a page is asked for a type, sources and a recheck.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.knowledge.entry import Finding

if TYPE_CHECKING:
    from coffer.infrastructure.knowledge.wiki import WikiGraph

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


def _link_findings(
    graph: WikiGraph,
    path: str,
    wiki: tuple[str, ...],
    relative: tuple[str, ...],
    inbound: dict[str, int],
) -> list[Finding]:
    """The findings on one file's links; counts the pages they reach."""
    found: list[Finding] = []
    for target in wiki:
        hits = graph.resolve(target)
        if not hits:
            found.append(Finding(DEAD_LINK, path, target))
        elif len(hits) > 1:
            found.append(Finding(AMBIGUOUS_LINK, path, target, tuple(hits)))
        elif hits[0] in inbound and hits[0] != path:
            inbound[hits[0]] += 1
    for target in relative:
        resolved, there = graph.follow(path, target)
        if resolved is None:
            found.append(Finding(OUTSIDE_LINK, path, target))
        elif not there:
            found.append(Finding(DEAD_LINK, path, target))
        elif resolved in inbound and resolved != path:
            inbound[resolved] += 1
    return found


def compute(graph: WikiGraph) -> list[Finding]:
    """Every mechanical finding of ``graph``, grouped by kind in
    :data:`FINDING_KINDS` order."""
    found: list[Finding] = []
    page_paths = {p.path for p in graph.pages}
    inbound: dict[str, int] = {p.path: 0 for p in graph.pages}
    for note in graph.notes:
        found += _link_findings(graph, note.path, note.links, note.path_links, inbound)
    for page in graph.pages:
        found += _link_findings(graph, page.path, page.links, page.path_links, inbound)
        cited = {path for slug in page.sources for path in graph.resolve_source(slug)}
        for slug in page.sources:
            hits = graph.resolve_source(slug)
            if not hits:
                found.append(Finding(MISSING_SOURCE, page.path, slug))
                continue
            old = graph.source(hits[0])
            if old is None or not old.superseded_by:
                continue
            later = graph.successors(old)
            if later and not cited & set(later):
                found.append(Finding(SUPERSEDED_SOURCE, page.path, slug, (later[-1],)))
        if page.missing_keys:
            found.append(Finding(INCOMPLETE_PAGE, page.path, ", ".join(page.missing_keys)))
        if graph.unsourced(page):
            found.append(Finding(UNSOURCED_PAGE, page.path))
        if graph.is_stale(page):
            found.append(Finding(STALE_PAGE, page.path, page.verified or None))
    for source in graph.sources:
        if source.superseded_by and not graph.resolve_source(source.superseded_by):
            found.append(Finding(MISSING_SOURCE, source.path, source.superseded_by))
    seen: set[tuple[str, ...]] = set()
    for alias, named in sorted(graph.names.items()):
        pages_named = sorted(h for h in named if h in page_paths)
        if len(pages_named) > 1 and tuple(pages_named) not in seen:
            seen.add(tuple(pages_named))
            found.append(Finding(DUPLICATE_SLUG, pages_named[0], alias, tuple(pages_named[1:])))
    if len(graph.pages) > 1:
        for page in graph.pages:
            if inbound[page.path] == 0 and page.page_type.lower() != OVERVIEW_TYPE:
                found.append(Finding(ORPHAN_PAGE, page.path))
    for source in graph.waiting():
        found.append(Finding(WAITING_SOURCE, source.path))
    order = {kind: i for i, kind in enumerate(FINDING_KINDS)}
    return sorted(found, key=lambda f: (order[f.kind], f.path, f.target or ""))


__all__ = [
    "AMBIGUOUS_LINK",
    "DEAD_LINK",
    "DUPLICATE_SLUG",
    "FINDING_KINDS",
    "INCOMPLETE_PAGE",
    "MISSING_SOURCE",
    "ORPHAN_PAGE",
    "OUTSIDE_LINK",
    "OVERVIEW_TYPE",
    "STALE_PAGE",
    "SUPERSEDED_SOURCE",
    "UNSOURCED_PAGE",
    "WAITING_SOURCE",
    "compute",
]
