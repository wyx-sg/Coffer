"""One collection read as a wiki: its pages, its sources and how they refer to
each other (spec knowledge "Link pages by slug and check every link", "Derive
which sources wait from the pages that cite them", "Check a collection
mechanically on every read").

:func:`build` walks a collection's ``pages/`` and ``sources/`` once and returns
a :class:`WikiGraph`. Nothing is stored: every read builds it again from the
files, so it cannot disagree with them (spec knowledge "Store each collection
as one tree of Markdown files"). A collection is hundreds of files at most, so
one walk is cheap.

A page's slug is its file stem, and a link names a slug or one of a page's
``aliases``. A ``sources`` entry names a source's slug. Matching ignores case
and Unicode width, the way file names are normalised (``naming.slugify``), and
tolerates a trailing ``.md`` or a leading folder, so a link written as a path
still resolves — the guide asks for slugs, but a reader should not be punished
for a near miss.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from coffer.domain.knowledge.entry import Finding, KnowledgeFile, LinkRef, PageRef, SourceRef
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

#: Finding kinds, in the order a surface lists them.
DEAD_LINK = "dead_link"
AMBIGUOUS_LINK = "ambiguous_link"
DUPLICATE_SLUG = "duplicate_slug"
MISSING_SOURCE = "missing_source"
INCOMPLETE_PAGE = "incomplete_page"
UNSOURCED_PAGE = "unsourced_page"
ORPHAN_PAGE = "orphan_page"
WAITING_SOURCE = "waiting_source"
FINDING_KINDS = (
    DEAD_LINK,
    AMBIGUOUS_LINK,
    DUPLICATE_SLUG,
    MISSING_SOURCE,
    INCOMPLETE_PAGE,
    UNSOURCED_PAGE,
    ORPHAN_PAGE,
    WAITING_SOURCE,
)

#: The page type exempt from the orphan check: an overview is an entry point.
OVERVIEW_TYPE = "overview"

#: The one key the guide lets an agent add to a source, and its one value.
INGEST_KEY = "ingest"
INGEST_SKIPPED = "skipped"

#: Keys a page must carry to be complete.
_REQUIRED_PAGE_KEYS = ("title", "type", "description")

_LINK = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|[^\[\]\n]*)?\]\]")
_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")


def normalise(name: str) -> str:
    """A slug, an alias or a link target in the form they are matched in."""
    text = unicodedata.normalize("NFKC", name or "").strip()
    text = text.rsplit("/", 1)[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text.strip().lower()


def _without_code(body: str) -> str:
    """The body with fenced blocks and inline code spans blanked, so a
    ``[[link]]`` written as an example is not a link."""
    out: list[str] = []
    fence: str | None = None
    for line in body.splitlines():
        opened = _FENCE.match(line)
        if fence is not None:
            if opened and opened.group(2)[0] == fence[0] and len(opened.group(2)) >= len(fence):
                fence = None
            out.append("")
            continue
        if opened:
            fence = opened.group(2)
            out.append("")
            continue
        out.append(_INLINE_CODE.sub(" ", line))
    return "\n".join(out)


def links_in(body: str) -> tuple[str, ...]:
    """Every ``[[target]]`` and ``[[target|text]]`` target outside code, in order."""
    return tuple(
        m.group(1).strip() for m in _LINK.finditer(_without_code(body)) if m.group(1).strip()
    )


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


@dataclass(frozen=True)
class Source:
    path: str
    slug: str
    title: str
    skipped: bool
    original: str | None


@dataclass
class WikiGraph:
    """A collection's pages and sources and the names they answer to."""

    pages: list[Page] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    #: Normalised page slug or alias → the pages it names.
    names: dict[str, set[str]] = field(default_factory=dict)
    #: Normalised source slug → the sources it names.
    source_names: dict[str, set[str]] = field(default_factory=dict)

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
        """Sources no page cites and none marks skipped."""
        cited = self.cited()
        return [s for s in self.sources if s.path not in cited and not s.skipped]

    def findings(self) -> list[Finding]:
        """Every mechanical finding, grouped by kind in :data:`FINDING_KINDS` order."""
        found: list[Finding] = []
        page_paths = {p.path for p in self.pages}
        inbound: dict[str, int] = {p.path: 0 for p in self.pages}
        for page in self.pages:
            for target in page.links:
                hits = self.resolve(target)
                if not hits:
                    found.append(Finding(DEAD_LINK, page.path, target))
                elif len(hits) > 1:
                    found.append(Finding(AMBIGUOUS_LINK, page.path, target, tuple(hits)))
                elif hits[0] in page_paths and hits[0] != page.path:
                    inbound[hits[0]] += 1
            for slug in page.sources:
                if not self.resolve_source(slug):
                    found.append(Finding(MISSING_SOURCE, page.path, slug))
            if page.missing_keys:
                found.append(Finding(INCOMPLETE_PAGE, page.path, ", ".join(page.missing_keys)))
            if not page.sources:
                found.append(Finding(UNSOURCED_PAGE, page.path))
        seen: set[tuple[str, ...]] = set()
        for alias, named in sorted(self.names.items()):
            pages_named = sorted(h for h in named if h in page_paths)
            if len(pages_named) > 1 and tuple(pages_named) not in seen:
                seen.add(tuple(pages_named))
                found.append(
                    Finding(DUPLICATE_SLUG, pages_named[0], alias, tuple(pages_named[1:]))
                )
        if len(self.pages) > 1:
            for page in self.pages:
                if inbound[page.path] == 0 and page.page_type.lower() != OVERVIEW_TYPE:
                    found.append(Finding(ORPHAN_PAGE, page.path))
        for source in self.waiting():
            found.append(Finding(WAITING_SOURCE, source.path))
        order = {kind: i for i, kind in enumerate(FINDING_KINDS)}
        return sorted(found, key=lambda f: (order[f.kind], f.path, f.target or ""))


def _markdown_under(directory: pathlib.Path) -> list[pathlib.Path]:
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


def _read(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    return split_frontmatter(text.replace("\r\n", "\n"))


def build(collection: str) -> WikiGraph:
    """Read a collection's pages and sources into a :class:`WikiGraph`."""
    graph = WikiGraph()
    for path in _markdown_under(paths.sources_dir(collection)):
        fm, _ = _read(path)
        source = Source(
            path=paths.relative_of(path),
            slug=path.stem,
            title=str(fm.get("title") or path.stem),
            skipped=str(fm.get(INGEST_KEY) or "").strip().lower() == INGEST_SKIPPED,
            original=str(fm["original"]) if fm.get("original") else None,
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
            sources=_as_list(fm.get("sources")),
            aliases=_as_list(fm.get("aliases")),
            links=links_in(body),
            missing_keys=tuple(k for k in _REQUIRED_PAGE_KEYS if not str(fm.get(k) or "").strip()),
        )
        graph.pages.append(page)
        for name in (page.slug, *page.aliases):
            graph.names.setdefault(normalise(name), set()).add(page.path)
    return graph


def describe(file: KnowledgeFile) -> KnowledgeFile:
    """``file`` with what the wiki says about it: a page's type, aliases,
    resolved sources and links; a source's citing pages, whether it waits and
    its kept original (spec knowledge "Link pages by slug and check every
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
        return dataclasses.replace(
            file,
            kind=kind,
            page_type=page.page_type,
            aliases=page.aliases,
            sources=tuple(sources),
            links=tuple(links),
        )
    source = graph.source(file.path)
    if source is None:
        return dataclasses.replace(file, kind=kind)
    original = None
    # A bare file name beside the source, never a path a writer could aim elsewhere.
    if source.original and pathlib.PurePath(source.original).name == source.original:
        candidate = pathlib.Path(file.folder_path) / source.original
        original = str(candidate) if candidate.is_file() else None
    return dataclasses.replace(
        file,
        kind=kind,
        cited_by=tuple(PageRef(p.path, p.title) for p in graph.citing(source.path)),
        waiting=any(s.path == source.path for s in graph.waiting()),
        original_path=original,
    )


__all__ = [
    "AMBIGUOUS_LINK",
    "DEAD_LINK",
    "DUPLICATE_SLUG",
    "FINDING_KINDS",
    "INCOMPLETE_PAGE",
    "INGEST_KEY",
    "INGEST_SKIPPED",
    "MISSING_SOURCE",
    "ORPHAN_PAGE",
    "OVERVIEW_TYPE",
    "UNSOURCED_PAGE",
    "WAITING_SOURCE",
    "Page",
    "Source",
    "WikiGraph",
    "build",
    "describe",
    "links_in",
    "normalise",
]
