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
#: Names joined by ``.`` or ``?.``: ``process.env.API_TOKEN``, ``args.token``.
_REFERENCE = re.compile(r"^[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)+$")
#: One name in a reference: letters and underscores, with digits only at its
#: end (``SPACE_TOKEN``, ``v2``). A random token's segments mix digits in.
_NAME = re.compile(r"^[A-Za-z_$][A-Za-z_$]*\d*$")
_MEMBER = re.compile(r"\??\.")
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
    text, which keeps the line's length), the name it is assigned to, the rule
    that found it, and its shape."""

    start: int
    end: int
    key: str
    #: The bundled rule that found it (spec secret "Detect plaintext secrets
    #: with the bundled rules").
    rule: str
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


def is_reference(value: str) -> bool:
    """Whether ``value`` reads as code naming a value rather than holding one:
    names joined by dots, such as an environment-variable read
    (``process.env.SPACE_TOKEN``) or a member (``args.token``,
    ``page.next_page_token``). A JSON Web Token (``eyJ…``) is dotted too, and
    is not one."""
    if value.startswith("eyJ") or not _REFERENCE.match(value):
        return False
    return all(_NAME.match(name) for name in _MEMBER.split(value))


def shape_of(value: str) -> ValueShape:
    """The shape a person judges ``value`` by."""
    prefix = _prefix(value)
    hint: str | None = None
    word: str | None = None
    lowered = value.lower()
    if is_reference(value):
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


def split_rows(text: str) -> list[str]:
    """The lines of ``text`` as a person reads them: split on ``\\n`` (the
    detector's line numbers), a trailing ``\\r`` and the empty last line of a
    final newline dropped."""
    rows = [row.removesuffix("\r") for row in text.split("\n")]
    if rows and rows[-1] == "":
        rows.pop()
    return rows


__all__ = [
    "MASK_CHAR",
    "MaskedValue",
    "ValueShape",
    "is_reference",
    "mask",
    "shape_of",
    "split_rows",
]
