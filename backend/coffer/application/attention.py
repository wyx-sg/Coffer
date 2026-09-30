"""The cross-kind "needs you" list the Overview page shows.

Each kind that can truthfully say something needs a person contributes an
:class:`AttentionSource`; :class:`AttentionService` asks every source whose
feature is switched on, isolates a source that fails (its section carries the
error, the others still answer), and sorts what comes back by severity.

An item names one resource, a stable ``reason_code`` with one sentence a
person can read, when the condition was first seen when anything knows that,
and **one** action: a verb and the REST route the kind's own page already uses
for it. The Overview therefore never has a write of its own — acting on an item
is the same call the item's page would make. An item whose fix is a chore for
an agent (installing a launcher, diagnosing a failing server) also carries the
kind's hand-off prompt, so the Overview row offers the same hand-off as the
page; its ``reason`` then names no command.

A source is added by the kind that owns the signal, registered at the
composition root. A signal nothing records yet (a provider key the endpoint
rejected) has no source: a list that reports only what the backend can know is
the contract, and a new source is the extension point.

**Ignoring.** An informational item — worth knowing, nothing broken, such as
an agent the person chose not to connect — can be ignored by its stable key
(:func:`attention_key`). The keys are kept on this machine by an
:class:`IgnoreStore`; an ignored item leaves ``items`` and ``counts_by_kind``
and is listed in ``ignored`` instead, so the Overview, the sidebar's badges and
the menu bar all count the same list. Something broken can never be ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from coffer.domain.attention_errors import AttentionNotIgnorable
from coffer.domain.audit import AuditEventType


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
    #: The prompt that hands this item's chore to an agent (``domain/handoff.py``),
    #: when it is one — the same text the kind's own page offers; ``None`` when
    #: the action alone is the fix.
    handoff: str | None = None


@dataclass(frozen=True)
class SourceError:
    """A source that raised; its items are missing from this answer."""

    source: str
    error: str


@dataclass(frozen=True)
class AttentionReport:
    items: tuple[AttentionItem, ...]
    errors: tuple[SourceError, ...] = ()
    #: How many items each kind has — the sidebar badges. Ignored items do not count.
    counts_by_kind: dict[str, int] = field(default_factory=dict)
    #: The items a person chose to ignore, still true but left out of ``items``.
    ignored: tuple[AttentionItem, ...] = ()


def attention_key(item: AttentionItem) -> str:
    """The stable key an item is ignored by: what it is about and why."""
    return f"{item.kind}:{item.uid or ''}:{item.reason_code}"


def ignorable(item: AttentionItem) -> bool:
    """Only an informational item can be ignored; a broken thing stays listed."""
    return item.severity is Severity.INFO


class IgnoreStore(Protocol):
    """The ignored keys, kept on this machine."""

    async def keys(self) -> set[str]: ...

    async def add(self, key: str) -> bool:
        """Remember ``key``; ``False`` when it was already there."""
        ...

    async def remove(self, key: str) -> bool:
        """Forget ``key``; ``False`` when it was not there."""
        ...


class AuditPort(Protocol):
    async def record(self, event_type: str, *, actor: str, details: dict[str, Any]) -> Any: ...


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
        ignores: IgnoreStore | None = None,
        audit: AuditPort | None = None,
    ) -> None:
        self._sources = tuple(sources)
        self._feature_enabled = feature_enabled
        self._ignores = ignores
        self._audit = audit

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self._sources)

    async def report(self) -> AttentionReport:
        """Ask every source that applies now. Writes nothing."""
        found: list[AttentionItem] = []
        errors: list[SourceError] = []
        for source in self._sources:
            if source.feature is not None and not self._feature_enabled(source.feature):
                continue
            try:
                found.extend(await source.items())
            except Exception as exc:
                errors.append(SourceError(source.name, repr(exc)))
        found.sort(key=lambda i: (_RANK[i.severity], i.kind, i.title, i.reason_code))
        keys = await self._ignores.keys() if self._ignores is not None else set()
        items: list[AttentionItem] = []
        ignored: list[AttentionItem] = []
        for item in found:
            (ignored if ignorable(item) and attention_key(item) in keys else items).append(item)
        counts: dict[str, int] = {}
        for item in items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return AttentionReport(tuple(items), tuple(errors), counts, tuple(ignored))

    async def ignore(self, key: str, *, actor: str) -> None:
        """Ignore the listed informational item ``key``. Raises
        :class:`AttentionNotIgnorable` for a key that names no such item now.
        Ignoring an ignored item again writes and audits nothing."""
        report = await self.report()
        if any(attention_key(i) == key for i in report.ignored):
            return
        item = next((i for i in report.items if attention_key(i) == key), None)
        if item is None or not ignorable(item) or self._ignores is None:
            raise AttentionNotIgnorable(key)
        if await self._ignores.add(key):
            await self._record(AuditEventType.ATTENTION_IGNORED, key, actor)

    async def unignore(self, key: str, *, actor: str) -> None:
        """Stop ignoring ``key``. A key that is not ignored is a no-op."""
        if self._ignores is not None and await self._ignores.remove(key):
            await self._record(AuditEventType.ATTENTION_UNIGNORED, key, actor)

    async def _record(self, event: AuditEventType, key: str, actor: str) -> None:
        if self._audit is not None:
            await self._audit.record(event.value, actor=actor, details={"key": key})


__all__ = [
    "AttentionAction",
    "AttentionItem",
    "AttentionReport",
    "AttentionService",
    "AttentionSource",
    "IgnoreStore",
    "Severity",
    "SourceError",
    "attention_key",
    "ignorable",
]
