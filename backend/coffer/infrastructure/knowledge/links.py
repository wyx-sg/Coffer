"""The links a knowledge file writes, found and resolved (spec knowledge "Link
pages by slug or relative path and check every link").

Two forms are links, and both are checked:

* ``[[target]]`` and ``[[target|text]]`` name a page's slug or alias, or a
  source's slug, and survive a move;
* a standard Markdown link or picture — ``[text](../pages/x.md)``,
  ``![chart](../assets/x/chart.png)``, or a reference definition
  ``[x]: ../pages/x.md`` — names a file by its path relative to the file that
  writes it, the way every Markdown reader, Obsidian and an agent's own file
  tools follow it.

A link with a scheme (``https:``, ``mailto:``) or a bare ``#anchor`` is not a
file link: it is left to whoever follows it. A relative link is resolved inside
the knowledge root, so a link from one collection into another is followed and
checked like any other; one that climbs out of the root is reported, never
followed. Nothing in a fenced block or an inline code span is a link.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import unquote

#: How a link names its target.
WIKI = "wiki"
PATH = "path"

_WIKI = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|[^\[\]\n]*)?\]\]")
#: ``[text](dest "title")`` and ``![alt](dest)``; ``dest`` may be ``<wrapped>``.
_INLINE = re.compile(
    r"!?\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\(\s*(<[^>\n]*>|[^)\s]+)(?:\s+[\"'(][^\n]*?[\"')])?\s*\)"
)
_REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]*>|\S+)", re.MULTILINE)
_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class Link:
    """One link as written: ``target`` is the slug, or the path as written
    (anchor and query dropped, percent-escapes decoded)."""

    kind: str
    target: str


def without_code(body: str) -> str:
    """The body with fenced blocks and inline code spans blanked, so a link
    written as an example is not a link."""
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


def wiki_links(body: str) -> tuple[str, ...]:
    """Every ``[[target]]`` and ``[[target|text]]`` target outside code, in order."""
    return tuple(
        m.group(1).strip() for m in _WIKI.finditer(without_code(body)) if m.group(1).strip()
    )


def file_target(destination: str) -> str | None:
    """The file a link destination names, as a relative path; ``None`` for a
    link off the knowledge (a scheme, ``//host``) or to an anchor only."""
    dest = destination.strip()
    if dest.startswith("<") and dest.endswith(">"):
        dest = dest[1:-1].strip()
    if not dest or dest.startswith("#") or dest.startswith("//") or _SCHEME.match(dest):
        return None
    dest = re.split(r"[?#]", dest, maxsplit=1)[0]
    return unquote(dest) or None


def path_links(body: str) -> tuple[str, ...]:
    """Every standard Markdown link, picture or reference definition outside
    code that names a file, as written relative to the file."""
    text = without_code(body)
    found = [m.group(1) for m in _INLINE.finditer(text)]
    found += [m.group(1) for m in _REFERENCE.finditer(text)]
    return tuple(t for t in (file_target(d) for d in found) if t)


def links_in(body: str) -> tuple[Link, ...]:
    """Both forms, wiki links first, each in the order written."""
    return tuple(Link(WIKI, t) for t in wiki_links(body)) + tuple(
        Link(PATH, t) for t in path_links(body)
    )


def resolve_path(from_file: str, target: str) -> str | None:
    """The knowledge-root-relative path ``target`` names when written in the
    file at ``from_file`` (itself knowledge-root-relative); ``None`` when it
    climbs out of the knowledge root. A target starting with ``/`` is read
    from the collection's own folder, as Obsidian reads one from its vault."""
    collection = from_file.strip("/").split("/", 1)[0]
    if target.startswith("/"):
        base, rest = collection, target.lstrip("/")
    else:
        base, rest = posixpath.dirname(from_file.strip("/")), target
    joined = posixpath.normpath(posixpath.join(base, rest)) if rest else base
    if joined in (".", "") or joined.startswith("../") or joined == ".." or joined.startswith("/"):
        return None
    return joined


__all__ = [
    "PATH",
    "WIKI",
    "Link",
    "file_target",
    "links_in",
    "path_links",
    "resolve_path",
    "wiki_links",
    "without_code",
]
