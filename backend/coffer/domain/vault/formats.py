"""Per-file format versions and their upgrade chains
(ADR every-vault-file-carries-its-format-version).

Every vault document Coffer parses carries an integer ``format_version`` for
its own kind. A kind declares its current version and a chain of pure upgrade
steps ``vN -> vN+1``, each marked **additive** (only new optional fields: an
older reader can still read the result) or **breaking**.

What a build does with a file depends on how its version compares:

- **current** — read and written normally;
- **older** — read through the chain *in memory*; an ordinary write never
  rewrites it at the new version (that is the owner machine's layout commit),
  so an edit to it is refused with the reason;
- **newer, readable** — the file says which oldest version can still read it
  (``format_compat``); at or above that, this build reads it, keeps the
  fields it does not know, and never writes, deletes or reconciles it;
- **newer, unreadable** — below ``format_compat``: this build keeps its last
  valid version of the resource and flags the file.

A document that never names ``format_compat`` is breaking by default: a build
must not guess that a future change was additive.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

FORMAT_VERSION_KEY = "format_version"
FORMAT_COMPAT_KEY = "format_compat"


class FormatStatus(StrEnum):
    CURRENT = "current"
    OLDER = "older"
    NEWER_READABLE = "newer_readable"
    NEWER_UNREADABLE = "newer_unreadable"

    @property
    def writable(self) -> bool:
        """Whether an ordinary write may replace a file in this status."""
        return self is FormatStatus.CURRENT


@dataclass(frozen=True)
class UpgradeStep:
    """One pure, deterministic step from ``from_version`` to the next."""

    from_version: int
    apply: Callable[[dict[str, Any]], dict[str, Any]]
    additive: bool


@dataclass(frozen=True)
class FormatSpec:
    """A document kind's current version and how to reach it."""

    current: int = 1
    steps: tuple[UpgradeStep, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        wanted = list(range(1, self.current))
        have = [s.from_version for s in self.steps]
        if have != wanted:
            raise ValueError(f"upgrade chain must cover 1..{self.current - 1} in order, got {have}")

    def compat_of(self, version: int) -> int:
        """The oldest version whose readers can read a file at ``version``:
        the last breaking step at or below it decides."""
        compat = 1
        for step in self.steps:
            if step.from_version < version and not step.additive:
                compat = step.from_version + 1
        return compat


@dataclass(frozen=True)
class Read:
    """A document as this build reads it."""

    doc: dict[str, Any]
    status: FormatStatus
    version: int


def version_of(raw: Mapping[str, Any]) -> int:
    """The document's ``format_version``; a document without one is ``1``."""
    value = raw.get(FORMAT_VERSION_KEY, 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{FORMAT_VERSION_KEY} must be a positive integer, got {value!r}")
    return value


def read(raw: Mapping[str, Any], spec: FormatSpec) -> Read:
    """Classify ``raw`` against ``spec`` and, for an older file, upgrade it in
    memory. The returned document is a copy; ``raw`` is never modified."""
    version = version_of(raw)
    doc = dict(raw)
    if version == spec.current:
        return Read(doc=doc, status=FormatStatus.CURRENT, version=version)
    if version > spec.current:
        compat = raw.get(FORMAT_COMPAT_KEY, version)
        readable = (
            isinstance(compat, int) and not isinstance(compat, bool) and compat <= spec.current
        )
        status = FormatStatus.NEWER_READABLE if readable else FormatStatus.NEWER_UNREADABLE
        return Read(doc=doc, status=status, version=version)
    for step in spec.steps:
        if step.from_version >= version:
            doc = step.apply(dict(doc))
            doc[FORMAT_VERSION_KEY] = step.from_version + 1
    return Read(doc=doc, status=FormatStatus.OLDER, version=version)


def stamp(doc: dict[str, Any], spec: FormatSpec) -> dict[str, Any]:
    """``doc`` stamped with this build's version (and its compat when a step
    below it was additive), for a file this build writes."""
    out = dict(doc)
    out[FORMAT_VERSION_KEY] = spec.current
    compat = spec.compat_of(spec.current)
    if compat < spec.current:
        out[FORMAT_COMPAT_KEY] = compat
    else:
        out.pop(FORMAT_COMPAT_KEY, None)
    return out


__all__ = [
    "FORMAT_COMPAT_KEY",
    "FORMAT_VERSION_KEY",
    "FormatSpec",
    "FormatStatus",
    "Read",
    "UpgradeStep",
    "read",
    "stamp",
    "version_of",
]
