"""draw.io diagrams found in a Confluence page, shown as what the page had
(spec knowledge "Import a Confluence page as a readable source with its
attachments").

* **An attached diagram** shows its picture, kept like any other attachment
  by the page converter.
* **A viewer link** stays the link it was; a reader clicks it to see the
  diagram.
* **A diagram drawn in the page** (an ``html`` macro holding draw.io's viewer
  markup, the diagram in its ``data-mxgraph`` attribute) becomes a viewer link
  carrying the diagram in its ``#R`` fragment, as draw.io's own "link" export
  does. A browser never sends a fragment to the server, so the diagram is drawn
  in the reader's browser and leaves the page no more than it did in
  Confluence.
* **A diagram that is a file elsewhere** (a viewer embed whose fragment starts
  ``#G`` for Google Drive, ``#U`` for a URL, ...) names a file Coffer has no
  access to: it is reported as an embed behind its owner's permission.

Coffer keeps no diagram source of its own, fetches nothing and draws nothing.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

_VIEWER_HOSTS = ("viewer.diagrams.net", "app.diagrams.net", "embed.diagrams.net", "draw.io")
#: The viewer a diagram with no picture opens in (draw.io's own lightbox).
VIEWER = "https://viewer.diagrams.net/?lightbox=1&nav=1#R"
_REMOTE_KINDS = {
    "G": "a Google Drive file",
    "U": "a file at another URL",
    "D": "a Dropbox file",
    "W": "a OneDrive file",
    "H": "a GitHub file",
}


def is_viewer(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _VIEWER_HOSTS)


def _deflate(xml: str) -> str:
    """draw.io's compressed form: base64 of raw deflate of URL-encoded XML."""
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = packer.compress(quote(xml, safe="-_.!~*'()").encode("ascii")) + packer.flush()
    return base64.b64encode(raw).decode("ascii")


def viewer_link(xml: str) -> str:
    """A link that opens ``xml`` in draw.io's viewer, the diagram in its fragment."""
    return VIEWER + quote(_deflate(xml), safe="")


def remote_kind(url: str) -> str | None:
    """What an embed names when its diagram is a file elsewhere (``#G…``),
    in words; ``None`` when it is not such an embed."""
    if not is_viewer(url):
        return None
    fragment = urlsplit(url).fragment
    return _REMOTE_KINDS.get(fragment[:1]) if fragment else "a diagram outside the page"


def from_html(markup: str) -> list[str]:
    """Every diagram an ``html`` macro carries inline (``data-mxgraph``), as
    draw.io XML, in order."""
    found: list[str] = []
    soup = BeautifulSoup(markup, "html.parser")
    for tag in [t for t in soup.find_all(True) if t.has_attr("data-mxgraph")]:
        try:
            config = json.loads(str(tag["data-mxgraph"]))
        except (ValueError, TypeError):
            continue
        xml = config.get("xml") if isinstance(config, dict) else None
        if isinstance(xml, str) and xml.strip():
            found.append(xml)
    return found


def embeds(markup: str) -> list[str]:
    """The ``src`` of every ``<iframe>`` in an ``html`` macro."""
    soup = BeautifulSoup(markup, "html.parser")
    return [str(tag.get("src") or "") for tag in soup.find_all("iframe") if tag.get("src")]


def readable_text(markup: str) -> str:
    """An ``html`` macro's own text, scripts, styles and embeds removed."""
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup.find_all(["script", "style", "iframe", "object", "embed", "noscript"]):
        tag.decompose()
    for tag in [t for t in soup.find_all(True) if t.has_attr("data-mxgraph")]:
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


__all__ = [
    "VIEWER",
    "embeds",
    "from_html",
    "is_viewer",
    "readable_text",
    "remote_kind",
    "viewer_link",
]
