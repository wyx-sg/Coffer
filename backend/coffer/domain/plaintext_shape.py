"""What a person may see of a value that looks like a plaintext secret
(spec vault-sync "Show a plaintext finding in its file").

The detection can be wrong — an example key, a test value, a line of code —
and only the person can tell. To let them tell without Coffer handing the
value out, a value is shown **masked**: every character becomes ``•``, so the
line keeps its length and the code around it reads as it is. What is shown in
its place is its shape, worked out here while the value is still in hand:

* its length and which kinds of character it holds;
* the public prefix of a well-known token format (``ghp_``, ``sk-``, ``AKIA``)
  or a URL's scheme — the vendor's marker, not part of the secret;
* a hint when it looks like something other than a secret: a code reference
  (names joined by dots, such as an environment-variable read), a placeholder
  word (``example``, ``dummy``, ``test`` …), or one character repeated.

No character of the value outside that prefix and that placeholder word is
returned, and nothing here writes anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MASK_CHAR = "•"

#: The well-known token formats whose prefix is public, longest first.
_PREFIXES = ("github_pat_", "ghp_", "gho_", "ghu_", "ghs_", "xoxa-", "xoxb-", "xoxp-", "xoxr-")
_PREFIX_RE = re.compile(r"^(?:sk-|AKIA|https?://)")
#: Names joined by dots: ``process.env.API_TOKEN``, ``settings.secret_key``.
_REFERENCE = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$")
_PLACEHOLDER_WORDS = (
    "example",
    "sample",
    "dummy",
    "placeholder",
    "changeme",
    "redacted",
    "fake",
    "test",
    "demo",
    "your",
    "todo",
    "xxx",
)


@dataclass(frozen=True)
class ValueShape:
    """What a masked value looks like, never what it is."""

    length: int
    #: Which of ``lower``, ``upper``, ``digit``, ``symbol`` it holds.
    classes: tuple[str, ...]
    #: A well-known token format's public prefix, or a URL's scheme.
    prefix: str | None = None
    #: ``reference`` / ``placeholder`` / ``repeated``; ``None`` reads as a value.
    hint: str | None = None
    #: For ``placeholder``: the placeholder word it contains.
    word: str | None = None


@dataclass(frozen=True)
class MaskedValue:
    """One masked value on a line: where it is (``[start, end)``, in the masked
    text, which keeps the line's length), the name it is assigned to, and its
    shape."""

    start: int
    end: int
    key: str
    shape: ValueShape


def _prefix(value: str) -> str | None:
    for p in _PREFIXES:
        if value.startswith(p):
            return p
    m = _PREFIX_RE.match(value)
    return m.group(0) if m else None


def _classes(value: str) -> tuple[str, ...]:
    out = []
    if any(c.islower() for c in value):
        out.append("lower")
    if any(c.isupper() for c in value):
        out.append("upper")
    if any(c.isdigit() for c in value):
        out.append("digit")
    if any(not c.isalnum() for c in value):
        out.append("symbol")
    return tuple(out)


def shape_of(value: str) -> ValueShape:
    """The shape a person judges ``value`` by."""
    prefix = _prefix(value)
    hint: str | None = None
    word: str | None = None
    lowered = value.lower()
    if _REFERENCE.match(value):
        hint = "reference"
    else:
        word = next((w for w in _PLACEHOLDER_WORDS if w in lowered), None)
        if word is not None:
            hint = "placeholder"
        elif len(set(value[len(prefix or "") :])) <= 2:
            hint = "repeated"
    return ValueShape(len(value), _classes(value), prefix, hint, word)


def mask(value: str, shape: ValueShape) -> str:
    """``value`` with every character past its public prefix replaced."""
    keep = len(shape.prefix or "")
    return value[:keep] + MASK_CHAR * (len(value) - keep)


__all__ = ["MASK_CHAR", "MaskedValue", "ValueShape", "mask", "shape_of"]
