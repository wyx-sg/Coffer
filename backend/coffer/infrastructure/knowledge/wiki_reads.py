"""What the wiki says about one file: a page's type, aliases, resolved sources
and links, and whether it is due a recheck; a source's citing pages, whether it
waits, what replaces it and its summary (spec knowledge "Link pages by slug or relative path and
check every link", "Derive which sources wait from the pages that cite them").
"""

from __future__ import annotations

import dataclasses

from coffer.domain.knowledge.entry import KnowledgeFile, LinkRef, PageRef, SourceRef
from coffer.infrastructure.knowledge import links as link_forms
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.wiki import WikiGraph, build


def _path_links(graph: WikiGraph, file: KnowledgeFile) -> tuple[LinkRef, ...]:
    """The file's links by relative path, each followed inside the knowledge
    root: to the file it names when one is there."""
    out: list[LinkRef] = []
    for target in dict.fromkeys(link_forms.path_links(file.body)):
        resolved, there = graph.follow(file.path, target)
        out.append(
            LinkRef(
                target=target,
                path=resolved if there else None,
                kind=link_forms.PATH,
                outside=resolved is None,
            )
        )
    return tuple(out)


def _wiki_links(graph: WikiGraph, targets: tuple[str, ...]) -> tuple[LinkRef, ...]:
    out: list[LinkRef] = []
    for target in dict.fromkeys(targets):
        hits = graph.resolve(target)
        out.append(
            LinkRef(
                target=target, path=hits[0] if len(hits) == 1 else None, ambiguous=len(hits) > 1
            )
        )
    return tuple(out)


def describe(file: KnowledgeFile) -> KnowledgeFile:
    """``file`` with what the wiki says about it: a page's type, aliases,
    resolved sources and links; a source's citing pages and whether it waits
    (spec knowledge "Link pages by slug or relative path and check every
    link", "Derive which sources wait from the pages that cite them")."""
    kind = paths.kind_of(file.path)
    markdown = file.path.endswith(".md")
    if kind == paths.KIND_FILE and not markdown:
        return dataclasses.replace(file, kind=kind)
    graph = build(paths.collection_of(file.path))
    path_links = _path_links(graph, file)
    if kind == paths.KIND_FILE:
        # A README, an index, a log: its links are followed like a page's.
        return dataclasses.replace(
            file, kind=kind, links=_wiki_links(graph, link_forms.wiki_links(file.body)) + path_links
        )
    titles = {p.path: p.title for p in graph.pages} | {s.path: s.title for s in graph.sources}
    if kind == paths.KIND_PAGE:
        page = graph.page(file.path)
        if page is None:
            return dataclasses.replace(file, kind=kind)
        sources = []
        for slug in page.sources:
            hits = graph.resolve_source(slug)
            hit = hits[0] if hits else None
            sources.append(SourceRef(slug=slug, path=hit, title=titles.get(hit or "", "")))
        links = _wiki_links(graph, page.links) + path_links
        return dataclasses.replace(
            file,
            kind=kind,
            page_type=page.page_type,
            aliases=page.aliases,
            verified=page.verified,
            stale=graph.is_stale(page),
            sources=tuple(sources),
            links=links,
        )
    source = graph.source(file.path)
    if source is None:
        return dataclasses.replace(file, kind=kind)
    successor = graph.successor(source)
    replaced = (
        SourceRef(slug=source.superseded_by, path=successor, title=titles.get(successor or "", ""))
        if source.superseded_by
        else None
    )
    return dataclasses.replace(
        file,
        kind=kind,
        cited_by=tuple(PageRef(p.path, p.title) for p in graph.citing(source.path)),
        waiting=any(s.path == source.path for s in graph.waiting()),
        superseded_by=replaced,
        summary=source.summary,
        links=path_links,
    )


__all__ = ["describe"]
