"""One collection read for its links: every Markdown file in it, the names a
``[[link]]`` may use for it, and every link that names nothing (spec knowledge
"Check every link in a collection").

This is all Coffer checks in a collection (ADR
knowledge-collections-own-their-format). Which keys a file carries, which
folders it sits in and what it must cite are the collection's own rules, which
agents follow from its rules file; a link that names nothing is broken whatever
the format, so that one is Coffer's to report.

:func:`build` walks a collection once and returns a :class:`LinkGraph`. Every
visible Markdown file is a file of the graph, and its slug (its file name
without ``.md``) and its frontmatter ``aliases`` are the names a ``[[link]]``
resolves against. A name more than one file answers to resolves to the one in
the linking file's own folder, the way a reader means the neighbour; with none
there it is ambiguous. Links are checked in every file except those under the
uploads folder: material Coffer imported keeps its links as its exporter wrote
them (a Confluence page's ``[[`` macros, say), so they are the source's record,
not the collection's to fix. Nothing is stored: every read builds it again from
the files, so it cannot disagree with them.

Matching ignores case and Unicode width, the way file names are normalised
(``naming.slugify``), and tolerates a trailing ``.md`` or a leading folder, so
a link written as a path still resolves.
"""

from __future__ import annotations

import os
import pathlib
import posixpath
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from coffer.domain.knowledge.entry import Finding
from coffer.infrastructure.knowledge import links as link_forms
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

#: Finding kinds, in the order a surface lists them.
DEAD_LINK = "dead_link"
AMBIGUOUS_LINK = "ambiguous_link"
OUTSIDE_LINK = "outside_link"
FINDING_KINDS = (DEAD_LINK, AMBIGUOUS_LINK, OUTSIDE_LINK)

ALIASES_KEY = "aliases"


def as_list(value: object) -> tuple[str, ...]:
    """A frontmatter list that a writer may have given as one string."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    if isinstance(value, Mapping):
        return tuple(str(k).strip() for k, v in value.items() if v not in (None, "", []))
    if isinstance(value, Iterable):
        return tuple(str(v).strip() for v in value if v is not None and str(v).strip())
    return (str(value),)


def normalise(name: str) -> str:
    """A slug, an alias or a link target in the form they are matched in."""
    text = unicodedata.normalize("NFKC", name or "").strip()
    text = text.rsplit("/", 1)[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text.strip().lower()


@dataclass(frozen=True)
class Doc:
    """One Markdown file and the links its body writes."""

    path: str
    links: tuple[str, ...]
    path_links: tuple[str, ...]
    #: Whether its links are checked: false under the uploads folder.
    checked: bool = True


@dataclass
class LinkGraph:
    """A collection's Markdown files and the names they answer to."""

    docs: list[Doc] = field(default_factory=list)
    #: Normalised slug or alias → the files it names.
    names: dict[str, set[str]] = field(default_factory=dict)

    def resolve(self, target: str, from_path: str = "") -> list[str]:
        """The files a ``[[target]]`` names, in path order; when several do,
        only those in ``from_path``'s own folder, if any are."""
        hits = sorted(self.names.get(normalise(target), ()))
        if len(hits) > 1 and from_path:
            folder = posixpath.dirname(from_path)
            near = [h for h in hits if posixpath.dirname(h) == folder]
            if near:
                return near
        return hits

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
        """Every broken link, grouped by kind in :data:`FINDING_KINDS` order."""
        found: list[Finding] = []
        for doc in self.docs:
            if not doc.checked:
                continue
            for target in doc.links:
                hits = self.resolve(target, doc.path)
                if not hits:
                    found.append(Finding(DEAD_LINK, doc.path, target))
                elif len(hits) > 1:
                    found.append(Finding(AMBIGUOUS_LINK, doc.path, target, tuple(hits)))
            for target in doc.path_links:
                resolved, there = self.follow(doc.path, target)
                if resolved is None:
                    found.append(Finding(OUTSIDE_LINK, doc.path, target))
                elif not there:
                    found.append(Finding(DEAD_LINK, doc.path, target))
        order = {kind: i for i, kind in enumerate(FINDING_KINDS)}
        return sorted(found, key=lambda f: (order[f.kind], f.path, f.target or ""))


def markdown_under(directory: pathlib.Path) -> list[pathlib.Path]:
    """Every visible Markdown file under ``directory``, in path order."""
    if not directory.is_dir():
        return []
    found: list[pathlib.Path] = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        found += [
            pathlib.Path(root) / f
            for f in sorted(filenames)
            if f.endswith(".md") and not f.startswith(".")
        ]
    return found


def build(collection: str) -> LinkGraph:
    """Read a collection's Markdown files into a :class:`LinkGraph`."""
    graph = LinkGraph()
    directory = paths.collection_dir(collection)
    uploads = paths.uploads_dir(collection)
    for path in markdown_under(directory):
        text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
        fm, body = split_frontmatter(text)
        doc = Doc(
            path=paths.relative_of(path),
            links=link_forms.wiki_links(body),
            path_links=link_forms.path_links(body),
            checked=not path.is_relative_to(uploads),
        )
        graph.docs.append(doc)
        is_readme = path.parent == directory and path.name == paths.README_NAME
        if is_readme:
            continue
        for name in (path.stem, *as_list(fm.get(ALIASES_KEY))):
            graph.names.setdefault(normalise(name), set()).add(doc.path)
    return graph


__all__ = [
    "AMBIGUOUS_LINK",
    "DEAD_LINK",
    "FINDING_KINDS",
    "OUTSIDE_LINK",
    "Doc",
    "LinkGraph",
    "build",
    "markdown_under",
    "normalise",
]
