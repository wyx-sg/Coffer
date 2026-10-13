"""What the wiki says about one file: a page's type, aliases, resolved sources
and links (wiki links, then standard links with the path each resolves to),
and whether it is due a recheck; a source's citing pages, whether it waits,
what replaces it and its summary (spec knowledge "Link pages by slug and check
every link", "Derive which sources wait from the pages that cite them").
"""

from __future__ import annotations

import dataclasses

from coffer.domain.knowledge.entry import (
    LINK_MARKDOWN,
    KnowledgeFile,
    LinkRef,
    PageRef,
    SourceRef,
)
from coffer.infrastructure.knowledge import paths, wiki_links
from coffer.infrastructure.knowledge.wiki import build


def describe(file: KnowledgeFile) -> KnowledgeFile:
    """``file`` with what the wiki says about it: a page's type, aliases,
    resolved sources and links; a source's citing pages and whether it waits
    (spec knowledge "Link pages by slug and check every
    link", "Derive which sources wait from the pages that cite them")."""
    kind = paths.kind_of(file.path)
    if kind == paths.KIND_FILE:
        return dataclasses.replace(file, kind=kind)
    graph = build(paths.collection_of(file.path))
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
        links = []
        for target in dict.fromkeys(page.links):
            hits = graph.resolve(target)
            links.append(
                LinkRef(
                    target=target,
                    path=hits[0] if len(hits) == 1 else None,
                    ambiguous=len(hits) > 1,
                )
            )
        for target in dict.fromkeys(page.doc_links):
            leads = wiki_links.resolve(page.path, target)
            links.append(
                LinkRef(target=target, path=leads.path, kind=LINK_MARKDOWN, outside=leads.outside)
            )
        return dataclasses.replace(
            file,
            kind=kind,
            page_type=page.page_type,
            aliases=page.aliases,
            verified=page.verified,
            stale=graph.is_stale(page),
            sources=tuple(sources),
            links=tuple(links),
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
    )


__all__ = ["describe"]
