"""Paths in a memory, made portable and expanded again (spec memory "Store
paths in a memory portably").

A memory says where things are in the words of the machine it was learned on:
``/Users/a/src/payments/ledger/retry.py``. On publish the repository root
becomes ``<repo>`` and the home directory ``~``; on write ``<repo>`` becomes
the project's checkout on the writing machine and ``~`` its home. Only whole
path prefixes are replaced: ``/Users/a/src/payments-old`` is not
``<repo>-old``. Any other path is left as written.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: The placeholder for the repository root a memory was learned in.
REPO = "<repo>"
#: The placeholder for the home directory.
HOME = "~"

#: What may follow a replaced prefix: the end of the text, a path separator,
#: or anything that cannot continue a file name.
_BOUNDARY_AFTER = r"(?=$|[/\s`'\"),;:\]>}]|\.(?:\s|$))"
#: What may precede one: the start of the text or anything that cannot be
#: part of a path.
_BOUNDARY_BEFORE = r"(?:(?<=^)|(?<=[\s`'\"(\[<{=:,]))"


def _prefix(root: str) -> str:
    return root.rstrip("/") if root not in ("", "/") else ""


def _replace(text: str, prefix: str, placeholder: str) -> str:
    pattern = re.compile(_BOUNDARY_BEFORE + re.escape(prefix) + _BOUNDARY_AFTER, re.MULTILINE)
    return pattern.sub(lambda _m: placeholder, text)


def to_portable(text: str, *, repo_roots: Iterable[str], home: str) -> str:
    """``text`` with each of ``repo_roots`` replaced by ``<repo>`` and then
    ``home`` by ``~``, the longest prefix first."""
    pairs = [(_prefix(r), REPO) for r in repo_roots if _prefix(r)]
    if _prefix(home):
        pairs.append((_prefix(home), HOME))
    for prefix, placeholder in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        text = _replace(text, prefix, placeholder)
    return text


_REPO_TOKEN = re.compile(re.escape(REPO) + _BOUNDARY_AFTER)
_HOME_TOKEN = re.compile(_BOUNDARY_BEFORE + re.escape(HOME) + r"(?=/|$|\s)", re.MULTILINE)


def from_portable(text: str, *, repo_root: str | None, home: str) -> str:
    """``text`` with ``<repo>`` expanded to ``repo_root`` (left as is when the
    memory is global) and ``~`` at the start of a path to ``home``."""
    if repo_root:
        root = repo_root.rstrip("/")
        text = _REPO_TOKEN.sub(lambda _m: root, text)
    if _prefix(home):
        text = _HOME_TOKEN.sub(lambda _m: _prefix(home), text)
    return text


__all__ = ["HOME", "REPO", "from_portable", "to_portable"]
