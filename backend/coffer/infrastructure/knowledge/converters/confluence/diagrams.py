"""Diagrams in a Confluence page: draw.io data read locally, hosted ones named.

A diagrams.net viewer link or iframe carries its diagram in the URL fragment:
``#R<data>`` is the diagram itself — ``encodeURIComponent`` of the mxfile XML,
or of draw.io's compressed form (base64 of a raw-deflated, URI-encoded XML) —
and is decoded here without any network. ``#G`` (Google Drive), ``#U`` (a URL)
and anything else name a diagram kept elsewhere, which is never fetched.
"""

from __future__ import annotations

import base64
import binascii
import json
import urllib.parse
import zlib

from coffer.infrastructure.knowledge.converters.confluence.kept import (
    EXTERNAL_EMBED,
    MAX_KEPT_BYTES,
    UNSUPPORTED,
    Kept,
    asset_link,
)

DIAGRAM_HOSTS = frozenset(
    {
        "viewer.diagrams.net",
        "app.diagrams.net",
        "embed.diagrams.net",
        "www.draw.io",
        "draw.io",
        "app.draw.io",
    }
)

_HOSTED_REASONS = {
    "G": "hosted on Google Drive; not fetched",
    "U": "hosted at another URL; not fetched",
    "D": "hosted on Dropbox; not fetched",
    "W": "hosted on OneDrive; not fetched",
    "H": "hosted on GitHub; not fetched",
}


def is_diagram_url(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    return host.lower() in DIAGRAM_HOSTS


def carries_diagram(url: str) -> bool:
    """Whether the URL's fragment is the diagram itself (``#R<data>``)."""
    return urllib.parse.urlsplit(url).fragment.startswith("R")


def _inflate(data: str) -> str | None:
    """draw.io's compressed form: base64 → raw deflate → URI-encoded XML."""
    try:
        raw = base64.b64decode(data, validate=False)
        inflater = zlib.decompressobj(-15)
        out = inflater.decompress(raw, MAX_KEPT_BYTES)
    except (binascii.Error, ValueError, zlib.error):
        return None
    if inflater.unconsumed_tail:
        return None
    try:
        return urllib.parse.unquote(out.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def as_mxfile(xml: str) -> bytes | None:
    """``xml`` as a file draw.io opens: an ``<mxfile>`` as-is, a bare
    ``<mxGraphModel>`` wrapped in one; ``None`` for anything else."""
    text = xml.strip()
    if text.startswith("<mxfile"):
        return text.encode("utf-8")
    if text.startswith("<mxGraphModel"):
        return f'<mxfile><diagram name="Page-1">{text}</diagram></mxfile>'.encode()
    return None


def decode_r(fragment: str) -> bytes | None:
    """The diagram a ``#R<data>`` fragment carries (``fragment`` without the
    ``#``), or ``None`` when it cannot be read."""
    if not fragment.startswith("R"):
        return None
    data = urllib.parse.unquote(fragment[1:])
    if not data.lstrip().startswith("<"):
        inflated = _inflate(data)
        if inflated is None:
            return None
        data = inflated
    return as_mxfile(data)


def _link_line(name: str) -> str:
    return f"[Diagram: {name}]({asset_link(name)})"


def diagram_url(kept: Kept, url: str, text: str = "") -> str:
    """Markdown for a diagrams.net URL: the decoded diagram kept and linked,
    or a line naming the hosted diagram (an ``external_embed``)."""
    fragment = urllib.parse.urlsplit(url).fragment
    if fragment.startswith("R"):
        data = decode_r(fragment)
        if data is not None:
            name = kept.diagram("drawio", data)
            if name is None:
                return f"*Diagram{': ' + text if text else ''} (draw.io source not kept)*"
            return _link_line(name)
        label = kept.next_diagram_label()
        kept.issue(EXTERNAL_EMBED, label, "its diagram data could not be read")
        return f"[Hosted diagram{': ' + text if text else ''}]({url})"
    label = kept.next_diagram_label()
    reason = _HOSTED_REASONS.get(fragment[:1], "hosted on diagrams.net; not fetched")
    kept.issue(EXTERNAL_EMBED, label, reason)
    return f"[Hosted diagram{': ' + text if text else ''}]({url})"


def mxgraph(kept: Kept, attribute: str) -> str:
    """Markdown for an inline ``data-mxgraph`` viewer: its ``xml`` kept as a
    ``.drawio`` file and linked."""
    try:
        config = json.loads(attribute)
    except ValueError:
        config = None
    xml = config.get("xml") if isinstance(config, dict) else None
    data = as_mxfile(xml) if isinstance(xml, str) else None
    if data is None:
        kept.issue(UNSUPPORTED, "html", "a draw.io viewer whose diagram data could not be read")
        return "*A draw.io diagram whose data could not be read was not kept.*"
    name = kept.diagram("drawio", data)
    if name is None:
        return "*Diagram (draw.io source not kept)*"
    return _link_line(name)
