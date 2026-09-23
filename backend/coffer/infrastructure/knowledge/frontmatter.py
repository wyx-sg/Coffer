"""YAML frontmatter parse/render for the on-disk markdown files.

A knowledge file self-describes with a ``---``-fenced YAML block. This module
is the only place that reads/writes a knowledge file's block (PyYAML lives here,
in infrastructure).

**Line endings are normalised, on purpose.** ``fs`` reads a file with
``Path.read_text``, which opens in universal-newline mode, so a CRLF file comes
back with LF and is written back with LF the next time an agent replaces it.
That is consistent with what :func:`render_frontmatter` already does — it
strips the body's surrounding blank lines and re-adds exactly one — because a
knowledge file is prose a human and an agent edit together, not a byte-exact
capture of something else. The memory layer, whose ``.raw/`` entries *are* a
byte-exact capture of an agent's own words, needs the opposite and therefore
has its own copy of this module rather than sharing it.
"""

from __future__ import annotations

from typing import Any

import yaml

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return ``(frontmatter_dict, body)``.

    If the text has no leading ``---`` fence, returns ``({}, text)``. A fenced
    block whose YAML is malformed degrades the same way — ``({}, body)`` with the
    fence stripped — rather than raising: a single hand-/agent-written file with
    a stray colon must not crash a whole store/KB scan. Callers fall back to
    filename / first-body-line defaults for the missing keys.

    The closing fence must sit at **column 0**. PyYAML serialises a long or
    multi-line string as an *indented* continuation, so a ``description`` whose
    text contains a horizontal rule puts ``    ---`` **inside** the block — and
    a scan that stripped each line before comparing would end the frontmatter
    there, silently returning a partial mapping and pushing the rest of the
    metadata into the body. Nothing in the vault trips it today only because
    every field a knowledge file carries is short: that is a property of the
    data, not of the parser, and an ingested document's generated description
    (spec knowledge "Fill frontmatter on converted material") is the field
    with no such guarantee.
    """
    if not text.startswith(_FENCE):
        return {}, text
    lines = text.split("\n")
    # lines[0] == '---'; find the closing fence — at column 0, see above.
    for i in range(1, len(lines)):
        if lines[i].rstrip() == _FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            try:
                loaded = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError:
                loaded = {}
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
