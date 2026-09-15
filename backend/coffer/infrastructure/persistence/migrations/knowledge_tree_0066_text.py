"""Frozen text helpers for migration 0066's on-disk rewrite.

A migration describes one moment in the schema's history, so the code it runs
must stay as it was at that moment. These are copies — not imports — of the
knowledge layer's ``naming``, ``frontmatter`` and ``paths`` helpers as they
stood on 2026-09-12, the day 0066 shipped. The live modules keep evolving with
the product; this file does not. Nothing here may import from ``coffer.*``.
"""

from __future__ import annotations

import os
import pathlib
import re
import unicodedata
from typing import Any

import yaml

README_NAME = "README.md"

_SEPARATORS = re.compile(r"[\s_/\\]+")
#: Keep CJK: transliterating it would produce a name neither party recognises.
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
MAX_SLUG_CHARS = 80

_FENCE = "---"


def knowledge_root() -> pathlib.Path:
    """The directory the knowledge layer lives in, as 0066 resolved it.

    ``$COFFER_KNOWLEDGE_ROOT`` wins when set (tests point it at a temp dir);
    otherwise ``$HOME/.coffer/knowledge``, with ``~`` expanded when ``HOME``
    is unset.
    """
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "knowledge"


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


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return ``(frontmatter_dict, body)``.

    No leading ``---`` fence, or a fenced block whose YAML is malformed,
    degrades to ``({}, body)`` rather than raising: one stray colon in one
    file must not fail a whole upgrade.
    """
    if not text.startswith(_FENCE):
        return {}, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
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
