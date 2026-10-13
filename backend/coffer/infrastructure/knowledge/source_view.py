"""How a source reads, beside what its file holds (spec knowledge "Import a
Confluence page as a readable source with its attachments").

A source written before Coffer read Confluence exports may still carry what
the export left: a second frontmatter block at the top of its body, and
storage markers (HTML comments holding Confluence XML) where a macro stood.
Reading such a source shows it the way a fresh import would — the block taken
out of the text and the markers converted — **without rewriting the file**:
what is on disk changes only when the person imports the page again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.infrastructure.knowledge.converters.confluence import markers
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

#: The keys of an origin a reader is shown, in order.
_ORIGIN_KEYS = ("system", "title", "url", "page_id", "space", "version", "fetched_at", "raw")
#: Where a Confluence export's own frontmatter says the same things.
_ALIASES = {"url": ("url", "origin", "source"), "fetched_at": ("fetched_at", "retrieved_at")}


def readable_body(body: str) -> str | None:
    """``body`` as a reader should see it, or ``None`` when it already reads
    as it is."""
    inner, rest = split_frontmatter(body)
    stripped = rest if inner else body
    expanded = markers.readable(stripped)
    if expanded is not None:
        return expanded
    return stripped if inner else None


def origin(fm: Mapping[str, Any], body: str) -> dict[str, str]:
    """Where a source came from, as plain strings: its ``origin`` mapping, or
    what an older export's own frontmatter (in the body) says."""
    found = fm.get("origin")
    if isinstance(found, Mapping):
        return {k: str(found[k]) for k in _ORIGIN_KEYS if found.get(k) not in (None, "")}
    inner, _ = split_frontmatter(body)
    source = inner or fm
    out: dict[str, str] = {}
    for key in _ORIGIN_KEYS:
        for alias in _ALIASES.get(key, (key,)):
            value = source.get(alias)
            if value not in (None, "") and not isinstance(value, Mapping | list):
                out[key] = str(value)
                break
    if "url" not in out:
        return {}
    return out


__all__ = ["origin", "readable_body"]
