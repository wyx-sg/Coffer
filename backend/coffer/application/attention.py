"""The cross-kind "needs you" list the Overview page shows.

Each kind that can truthfully say something needs a person contributes an
:class:`AttentionSource`; :class:`AttentionService` asks every source whose
feature is switched on, isolates a source that fails (its section carries the
error, the others still answer), and sorts what comes back by severity.

An item names one resource, a stable ``reason_code`` with one sentence a
person can read, when the condition was first seen when anything knows that,
and **one** action: a verb and the REST route the kind's own page already uses
for it. The Overview therefore never has a write of its own — acting on an item
is the same call the item's page would make.

A source is added by the kind that owns the signal, registered at the
composition root. A signal nothing records yet (a provider key the endpoint
rejected) has no source: a list that reports only what the backend can know is
the contract, and a new source is the extension point.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class Severity(StrEnum):
    """How urgently an item needs a person, most urgent first."""

    #: Something Coffer promises is not working now.
    ERROR = "error"
    #: Something is out of step and will stay so without a person.
    WARNING = "warning"
    #: Worth knowing; nothing is broken.
    INFO = "info"


_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True)
class AttentionAction:
    """The one thing a person can do about an item: the route the kind's
    own page calls, with the body it sends (``None`` for none)."""

    verb: str
    method: str
    path: str
    body: dict[str, Any] | None = None


@dataclass(frozen=True)
class AttentionItem:
    kind: str
    uid: str | None
    title: str
    reason_code: str
    reason: str
    severity: Severity
    action: AttentionAction
    since: datetime | None = None


@dataclass(frozen=True)
class SourceError:
    """A source that raised; its items are missing from this answer."""

    source: str
    error: str


@dataclass(frozen=True)
class AttentionReport:
    items: tuple[AttentionItem, ...]
    errors: tuple[SourceError, ...] = ()
    #: How many items each kind has — the sidebar badges.
    counts_by_kind: dict[str, int] = field(default_factory=dict)


class AttentionSource(Protocol):
    """One kind's contribution to the list."""

    @property
    def name(self) -> str: ...

    @property
    def feature(self) -> str | None:
        """The experimental feature this source belongs to; ``None`` when it
        belongs to none and is always asked."""
        ...

    async def items(self) -> Sequence[AttentionItem]: ...


class AttentionService:
    def __init__(
        self,
        sources: Sequence[AttentionSource],
        *,
        feature_enabled: Callable[[str], bool],
    ) -> None:
        self._sources = tuple(sources)
        self._feature_enabled = feature_enabled

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self._sources)

    async def report(self) -> AttentionReport:
        """Ask every source that applies now. Writes nothing."""
        items: list[AttentionItem] = []
        errors: list[SourceError] = []
        for source in self._sources:
            if source.feature is not None and not self._feature_enabled(source.feature):
                continue
            try:
                items.extend(await source.items())
            except Exception as exc:
                errors.append(SourceError(source.name, repr(exc)))
        items.sort(key=lambda i: (_RANK[i.severity], i.kind, i.title, i.reason_code))
        counts: dict[str, int] = {}
        for item in items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return AttentionReport(tuple(items), tuple(errors), counts)


__all__ = [
    "AttentionAction",
    "AttentionItem",
    "AttentionReport",
    "AttentionService",
    "AttentionSource",
    "Severity",
    "SourceError",
]
