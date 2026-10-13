"""Storage markers in a Markdown export (design §6).

A Markdown export of a Confluence page leaves each macro it could not convert
as an HTML comment: ``<!-- skynet-confluence-storage:v1 kind=… \\n<xml>\\n-->``,
with every ``-`` of a ``--`` inside the XML written ``\\u002d`` (so the comment
stays closed) and every backslash doubled. :func:`expand_storage_markers`
replaces each such block by the Storage → Markdown conversion of its XML. The
export keeps no files, so a picture or diagram it names is listed
``missing_attachment``. Text outside the markers is left as it is.
"""

from __future__ import annotations

import re

from coffer.domain.knowledge.converter import ConversionIssue
from coffer.infrastructure.knowledge.converters.confluence.kept import Kept
from coffer.infrastructure.knowledge.converters.confluence.storage import Walker

STORAGE_MARKER = "skynet-confluence-storage:v1"

_MARKER = re.compile(
    r"<!--[ \t]*skynet-confluence-storage:v1\b[^\n]*\n(?P<xml>.*?)\n?[ \t]*-->(?P<after>\n*)",
    re.S,
)
_ESCAPE = re.compile(r"\\(u002d|\\)")


def unescape_marker(xml: str) -> str:
    """The Storage XML a marker carries: ``\\u002d`` → ``-``, ``\\\\`` → ``\\``."""
    return _ESCAPE.sub(lambda m: "-" if m.group(1) == "u002d" else "\\", xml)


def expand_storage_markers(markdown: str) -> tuple[str, tuple[ConversionIssue, ...]]:
    """``markdown`` with every storage marker replaced by readable Markdown,
    and what the expansion could not keep."""
    if STORAGE_MARKER not in markdown:
        return markdown, ()
    walker = Walker(Kept(keep_files=False))
    out: list[str] = []
    cursor = 0
    for match in _MARKER.finditer(markdown):
        out.append(markdown[cursor : match.start()])
        cursor = match.end()
        xml = unescape_marker(match.group("xml"))
        converted = walker.markdown(xml).strip()
        if not converted:
            continue
        before = "".join(out)
        if before and not before.endswith("\n\n"):
            out.append("\n" if before.endswith("\n") else "\n\n")
        out.append(converted)
        if cursor < len(markdown):
            out.append("\n\n")
    out.append(markdown[cursor:])
    return "".join(out), tuple(walker.kept.issues)
