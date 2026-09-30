"""Version numbers as a ``--version`` prints them, and how two compare.

Kind-agnostic: agent detection reads a program's version with it, and a
skill's required command is compared with the minimum the skill asks for. A
version is dotted numbers — ``2.40``, ``0.4.18`` — optionally followed by a
pre-release or build tag, which the comparison ignores.
"""

from __future__ import annotations

import re

_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.\-]+)?")
_LEADING_NUMBERS = re.compile(r"^\d+(?:\.\d+)*")


def parse_version(output: str) -> str | None:
    """The first version number in a ``--version`` output.

    ``2.1.281 (Claude Code)`` and ``codex-cli 0.155.1`` both carry exactly one;
    anything without a dotted number is not a version the probe claims.
    """
    match = _VERSION.search(output)
    return match.group(0) if match else None


def version_numbers(version: str) -> tuple[int, ...] | None:
    """``"0.4.18"`` → ``(0, 4, 18)``; the numbers a version starts with, or
    ``None`` when it does not start with one. ``"2.40-rc1"`` → ``(2, 40)``."""
    match = _LEADING_NUMBERS.match(version.strip().lstrip("vV"))
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def compare_versions(a: str, b: str) -> int | None:
    """``-1``, ``0`` or ``1`` as ``a`` is below, equal to or above ``b``;
    ``None`` when either cannot be read. Missing trailing parts count as zero,
    so ``0.4`` equals ``0.4.0``."""
    left, right = version_numbers(a), version_numbers(b)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    lp = left + (0,) * (width - len(left))
    rp = right + (0,) * (width - len(right))
    return (lp > rp) - (lp < rp)


def at_least(found: str, minimum: str) -> bool | None:
    """Whether ``found`` meets ``minimum``; ``None`` when either is unreadable."""
    order = compare_versions(found, minimum)
    return None if order is None else order >= 0


__all__ = ["at_least", "compare_versions", "parse_version", "version_numbers"]
