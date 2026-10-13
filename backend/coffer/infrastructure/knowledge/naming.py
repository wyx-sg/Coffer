"""File naming — the path is the identity (spec knowledge "Use the file path as a
document's identity").

With no index mapping an id to a title, a file name is what a human reads in
their file manager and what an agent reads in a grep result. So names are
slugs derived from the title, not opaque ids.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata

_SEPARATORS = re.compile(r"[\s_/\\]+")
#: Keep CJK: transliterating it would produce a name neither party recognises.
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
MAX_SLUG_CHARS = 80


def slugify(title: str) -> str:
    """A readable, path-safe stem for a title. Never empty."""
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    stem = _DASHES.sub("-", _DROP.sub("", _SEPARATORS.sub("-", normalized))).strip("-")
    return (stem or "untitled")[:MAX_SLUG_CHARS].strip("-") or "untitled"


def unique_name(directory: pathlib.Path, slug: str) -> str:
    """``<slug>.md``, suffixed only when that name is already taken."""
    if not (directory / f"{slug}.md").exists():
        return f"{slug}.md"
    for n in range(2, 1000):
        candidate = f"{slug}-{n}.md"
        if not (directory / candidate).exists():
            return candidate
    raise ValueError(f"cannot find a free name for {slug!r}")


#: Length of the opening-prose fallback description: a catalogue line, not a summary.
FALLBACK_DESCRIPTION_CHARS = 240


#: How a block that is not prose opens: a heading, a table, HTML, a picture, a
#: quote, a code fence or a rule.
_TABLE_OPEN = re.compile(r"<table\b", re.IGNORECASE)
_TABLE_CLOSE = re.compile(r"</table>", re.IGNORECASE)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_EMPHASIS_ONLY = re.compile(r"(\*\*|__|\*|_)(?!\s).+?\1:?")
_LIST_ITEM = re.compile(r"([-*+]|\d+[.)])\s")
_PLACEHOLDER = re.compile(r"\\?\[[^\]]*\\?\]")
_LABEL = re.compile(r"[^:\uff1a.\u3002]{1,40}[:\uff1a][\s/,|()-]*")
_NOT_PROSE = ("#", "|", "<", "![", ">", "```", "~~~", "---", "***")


def opening_prose(markdown: str, *, fallback: str) -> str:
    """A document's own opening prose — its first paragraph that is prose, with
    headings, lists, tables, HTML, pictures, quotes and code skipped — or ``fallback``
    (its title) when it has none: a bare table, a blank file.

    The description a catalogue entry needs when nothing wrote one (spec
    knowledge "Fill frontmatter on converted material").
    """
    paragraph: list[str] = []
    skipping = False
    fence: str | None = None
    tables = 0
    for line in markdown.splitlines():
        stripped = line.strip()
        # An HTML table's cells may hold Markdown set off by blank lines: none
        # of it is the document's opening prose.
        tables += len(_TABLE_OPEN.findall(stripped)) - len(_TABLE_CLOSE.findall(stripped))
        if tables > 0 or _TABLE_CLOSE.search(stripped):
            tables = max(tables, 0)
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            continue
        if not stripped:
            if paragraph and _is_sentence(paragraph):
                return " ".join(paragraph)[:FALLBACK_DESCRIPTION_CHARS]
            paragraph = []
            skipping = False
            continue
        if skipping:
            continue
        if not paragraph and (stripped.startswith(_NOT_PROSE) or _LIST_ITEM.match(stripped)):
            skipping = not stripped.startswith("#")
            continue
        paragraph.append(stripped)
    if paragraph and _is_sentence(paragraph):
        return " ".join(paragraph)[:FALLBACK_DESCRIPTION_CHARS]
    return fallback


def _is_sentence(lines: list[str]) -> bool:
    """Whether a paragraph says something in words rather than being a bare
    link, an emphasised label or notice, a ``[placeholder]``, or lines that
    are each a ``label: <links>``."""
    text = " ".join(lines)
    if not _LINK.sub(" ", text).strip():
        return False
    if _EMPHASIS_ONLY.fullmatch(text) or _PLACEHOLDER.fullmatch(text):
        return False
    return not all(_LABEL.fullmatch(_LINK.sub(" ", line).rstrip("\\ ")) for line in lines)
