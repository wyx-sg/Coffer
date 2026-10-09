"""The last redaction pass over a call's recorded content: the bundled
plaintext-secret rules (spec mcp-gateway "Record invocations with redacted,
bounded content").

The gateway has already masked what Coffer injected, credential headers and
secret-named fields (``domain.activity_content``); this catches what neither
knew about — a key an agent pasted into an argument, a token an upstream
minted and returned. It runs in the invocation writer, off the event loop,
over each part's recorded JSON, and replaces each finding's value in place.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.activity_content import MASK
from coffer.infrastructure.secret.detector import detect


def scrub_text(text: str) -> str:
    """``text`` with every value the rules find replaced by :data:`MASK`."""
    found = detect(text)
    if not found:
        return text
    out: list[str] = []
    pos = 0
    for d in found:
        out.append(text[pos : d.start])
        out.append(MASK)
        pos = d.end
    out.append(text[pos:])
    return "".join(out)


def scrub_content(content: dict[str, Any] | None) -> dict[str, Any] | None:
    """Every part of one call's content, scrubbed; sizes and cut flags kept."""
    if not content:
        return content
    return {
        name: {**part, "text": scrub_text(part["text"])} if isinstance(part, dict) else part
        for name, part in content.items()
    }


__all__ = ["scrub_content", "scrub_text"]
