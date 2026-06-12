"""YAML frontmatter parse/render for the on-disk markdown files.

Both faces self-describe with a ``---``-fenced YAML block. This module is the
only place that reads/writes that block (PyYAML lives here, in infrastructure).
"""

from __future__ import annotations

from typing import Any

import yaml

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return ``(frontmatter_dict, body)``.

    If the text has no leading ``---`` fence, returns ``({}, text)``.
    """
    if not text.startswith(_FENCE):
        return {}, text
    lines = text.split("\n")
    # lines[0] == '---'; find the closing fence.
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            loaded = yaml.safe_load(raw) if raw.strip() else {}
            fm = loaded if isinstance(loaded, dict) else {}
            return fm, body.lstrip("\n")
    return {}, text


def render_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    """Render a ``---``-fenced YAML block + body. Keys keep insertion order."""
    block = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip("\n")
    body_clean = body.strip("\n")
    return f"{_FENCE}\n{block}\n{_FENCE}\n\n{body_clean}\n"


def body_of(text: str) -> str:
    """The markdown body only (frontmatter stripped)."""
    _, body = split_frontmatter(text)
    return body
