"""draw.io diagrams found in a Confluence page, told apart by what can be kept.

Three shapes reach a page, and each ends differently (spec knowledge "Import a
Confluence page as a readable source with its attachments"):

* **The diagram is in the page.** An ``html`` macro holding draw.io's viewer
  markup carries the whole diagram in its ``data-mxgraph`` attribute, and a
  viewer link whose fragment starts ``#R`` carries it in the URL. Both are
  decoded here into the ``.drawio`` file draw.io itself opens, kept beside the
  source.
* **The diagram is a file elsewhere.** A viewer link or ``<iframe>`` whose
  fragment starts ``#G`` (Google Drive), ``#U`` (a URL), ``#D`` (Dropbox) or
  ``#W`` (OneDrive) names a file Coffer has no access to and does not fetch:
  it is reported as an embed behind its owner's permission.
* **The diagram is an attachment** of the page (the ``drawio`` macro) and is
  kept like any other attachment, by the page converter.

Nothing is sent to a rendering service: Coffer keeps a diagram's source and
any picture the page already had, and draws nothing itself.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

_VIEWER_HOSTS = ("viewer.diagrams.net", "app.diagrams.net", "embed.diagrams.net", "draw.io")
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


def _inflate(data: str) -> str | None:
    """draw.io's compressed form: base64 of raw deflate of URL-encoded XML."""
    try:
        raw = base64.b64decode(data, validate=False)
        return unquote(zlib.decompress(raw, -15).decode("utf-8"))
    except (binascii.Error, zlib.error, UnicodeDecodeError, ValueError):
        return None


def from_viewer_link(url: str) -> str | None:
    """The diagram a viewer link carries in its ``#R`` fragment, as draw.io
    XML; ``None`` for any other link."""
    if not is_viewer(url):
        return None
    fragment = urlsplit(url).fragment
    if not fragment.startswith("R"):
        return None
    data = unquote(fragment[1:]).strip()
    if data.startswith("<"):
        return data
    return _inflate(data)


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


__all__ = ["embeds", "from_html", "from_viewer_link", "is_viewer", "readable_text", "remote_kind"]
