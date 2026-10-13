"""Markdown that still carries Confluence storage inside HTML comments, made
readable (spec knowledge "Import a Confluence page as a readable source with
its attachments").

A Confluence command-line tool that writes Markdown keeps what it could not
convert as a fidelity marker: an HTML comment holding the original storage,

    <!-- skynet-confluence-storage:v1 kind=structured-macro
    <ac:structured-macro ac:name="numberedheadings">…</ac:structured-macro>
    -->

The marker is the page's text, not noise: a ``numberedheadings`` macro wrapped
round a whole page leaves *all* of it inside one. So a marker is never stripped
for looking like markup. :func:`expand` converts each one's storage the way an
imported page is converted, in place, and :func:`storage_of` gives the raw
storage back so it can be kept for tracing. A comment that is not such a marker
is left as it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coffer.infrastructure.knowledge.converters.confluence import storage
from coffer.infrastructure.knowledge.converters.confluence.context import Context

#: ``<!-- <tool>-confluence-storage:v<n> [attributes]`` … ``-->``.
#: The closing ``-->`` stands on a line of its own, so one inside the storage
#: (a ``CDATA`` holding an HTML comment) does not end the marker early.
_MARKER = re.compile(
    r"<!--[ \t]*([A-Za-z0-9_.-]*confluence-storage):v\d+[^\n]*\n(.*?)\n[ \t]*-->[ \t]*(?=\n|$)",
    re.DOTALL,
)
#: How a marker writes ``--`` inside a comment, which may not hold one.
_ESCAPED_DASHES = (("&#45;", "-"), ("&#x2d;", "-"), ("&#x2D;", "-"), ("-\\-", "--"))


@dataclass(frozen=True)
class Expanded:
    markdown: str
    #: The storage each marker held, in order.
    storage: tuple[str, ...]


def has_markers(markdown: str) -> bool:
    return _MARKER.search(markdown) is not None


def _unescape(xml: str) -> str:
    for escaped, plain in _ESCAPED_DASHES:
        xml = xml.replace(escaped, plain)
    return xml


def expand(markdown: str, ctx: Context) -> Expanded:
    """``markdown`` with every storage marker replaced by its readable form."""
    kept: list[str] = []

    def _one(match: re.Match[str]) -> str:
        xml = _unescape(match.group(2))
        kept.append(xml)
        return "\n" + storage.convert(xml, ctx).strip() + "\n"

    return Expanded(markdown=_MARKER.sub(_one, markdown), storage=tuple(kept))


def readable(markdown: str) -> str | None:
    """``markdown`` as a reader should see it when it still carries markers
    (a source imported before they were converted), else ``None``. Nothing is
    written: the file keeps its markers until it is imported again."""
    if not has_markers(markdown):
        return None
    return expand(markdown, Context(folder="", keeps_files=False)).markdown


def storage_of(markdown: str) -> tuple[str, ...]:
    return tuple(_unescape(m.group(2)) for m in _MARKER.finditer(markdown))


__all__ = ["Expanded", "expand", "has_markers", "readable", "storage_of"]
