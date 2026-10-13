"""The two kinds of link a collection's Markdown holds, read out of a body and
resolved (spec knowledge "Link pages by slug and check every link").

A **wiki link** is ``[[target]]`` or ``[[target|text]]`` and names a slug or an
alias; :class:`~coffer.infrastructure.knowledge.wiki.WikiGraph` resolves it. A
**standard link** is a Markdown link or image, ``[text](target)`` or
``![alt](target)`` (the target may be written ``<target>`` and followed by a
title), and names a path relative to the file that holds it; :func:`resolve`
resolves it here, against the knowledge root, without following anything out
of it.

Both are read outside code: fenced blocks and inline code spans are blanked
first, so an example is not a link.
"""

from __future__ import annotations

import posixpath
import re
import urllib.parse
from dataclasses import dataclass

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import paths

_WIKI = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|[^\[\]\n]*)?\]\]")
_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")

#: ``[text](target "title")`` and its image form. The text may hold one level
#: of brackets, so ``[![alt](pic.png)](page.md)`` reads as the outer link; the
#: inner image is read from the text again.
_MARKDOWN = re.compile(
    r"!?\[(?P<text>(?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]"
    r"\(\s*(?:<(?P<angle>[^<>\n]*)>|(?P<bare>[^\s()<>]+(?:\([^\s()]*\)[^\s()<>]*)*))"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?\s*\)"
)
#: A URL scheme: ``http:``, ``mailto:``, ``coffer-asset:`` and the like.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


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


def links_in(body: str) -> tuple[str, ...]:
    """Every ``[[target]]`` and ``[[target|text]]`` target outside code, in order."""
    return tuple(
        m.group(1).strip() for m in _WIKI.finditer(without_code(body)) if m.group(1).strip()
    )


def _markdown_targets(text: str) -> list[str]:
    found: list[str] = []
    for m in _MARKDOWN.finditer(text):
        found += _markdown_targets(m.group("text"))
        target = (m.group("angle") if m.group("angle") is not None else m.group("bare")) or ""
        if target.strip():
            found.append(target.strip())
    return found


def is_external(target: str) -> bool:
    """A target Coffer never checks: it has a URL scheme or is an anchor."""
    return target.startswith("#") or bool(_SCHEME.match(target))


def markdown_links_in(body: str) -> tuple[str, ...]:
    """Every standard link and image target outside code that names a path —
    external targets (a URL scheme, ``#anchor``) left out — as written, in order."""
    return tuple(t for t in _markdown_targets(without_code(body)) if not is_external(t))


@dataclass(frozen=True)
class Resolved:
    """Where a standard link leads: ``path`` the knowledge-root-relative file
    it names when that exists; ``outside`` when it leaves the knowledge root."""

    path: str | None = None
    outside: bool = False


def resolve(holder: str, target: str) -> Resolved:
    """Resolve ``target``, a standard link in the file at knowledge-root-relative
    ``holder``: percent-decoded, its ``#fragment`` and ``?query`` dropped,
    relative to ``holder``'s directory.

    An absolute path, one that climbs above the root, or one whose existing
    part is a symlink out of it is ``outside``. A hidden entry is never
    addressable, so a link to one names nothing.
    """
    text = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()
    if not text:
        # Only a query or a fragment: the file itself.
        return Resolved(path=holder)
    if text.startswith("/") or text.startswith("\\"):
        return Resolved(outside=True)
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(holder), text))
    if joined in ("", ".") or joined == ".." or joined.startswith("../"):
        return Resolved(outside=True)
    if any(segment.startswith(".") for segment in joined.split("/")):
        return Resolved()
    candidate = paths.knowledge_root().joinpath(*joined.split("/"))
    try:
        paths.assert_inside_root(candidate, joined)
    except UnsafeKnowledgePath:
        return Resolved(outside=True)
    return Resolved(path=joined if candidate.exists() else None)


__all__ = [
    "Resolved",
    "is_external",
    "links_in",
    "markdown_links_in",
    "resolve",
    "without_code",
]
