"""The links one file writes, each resolved to the file it names (spec
knowledge "Check every link in a collection"), so a surface can follow them.
"""

from __future__ import annotations

import dataclasses

from coffer.domain.knowledge.entry import KnowledgeFile, LinkRef
from coffer.infrastructure.knowledge import links as link_forms
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.link_graph import LinkGraph, build


def _path_links(graph: LinkGraph, file: KnowledgeFile) -> tuple[LinkRef, ...]:
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


def _wiki_links(graph: LinkGraph, file: KnowledgeFile) -> tuple[LinkRef, ...]:
    out: list[LinkRef] = []
    for target in dict.fromkeys(link_forms.wiki_links(file.body)):
        hits = graph.resolve(target, file.path)
        out.append(
            LinkRef(
                target=target, path=hits[0] if len(hits) == 1 else None, ambiguous=len(hits) > 1
            )
        )
    return tuple(out)


def describe(file: KnowledgeFile) -> KnowledgeFile:
    """``file`` with its links resolved; a file that is not Markdown as it is.

    A file in the uploads folder is material kept as it arrived, so its
    ``[[`` text (a Confluence macro, say) is not read as links: only its
    relative links are followed, the way a reader would click them."""
    if not file.path.endswith(".md"):
        return file
    collection = paths.collection_of(file.path)
    graph = build(collection)
    uploaded = paths.resolve(file.path).is_relative_to(paths.uploads_dir(collection))
    wiki = () if uploaded else _wiki_links(graph, file)
    return dataclasses.replace(file, links=wiki + _path_links(graph, file))


__all__ = ["describe"]
