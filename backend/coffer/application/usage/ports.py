"""Ports the usage services depend on, and the rows they pass across them (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

The application layer never imports infrastructure: the SQLAlchemy repo and
the spool reader adapt these Protocols, and ``surfaces/http/usage_wiring.py``
composes them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from coffer.domain.usage.pricing import ResolvedPrice
from coffer.domain.usage.records import UsageRecord

# -- rows ----------------------------------------------------------------------


@dataclass(frozen=True)
class PricedRecord:
    """A spooled record with the cost computed at ingest and the local day it
    rolls up into. ``cost_usd`` is ``None`` when usage is unknown or the model
    is unpriced; ``unpriced`` says which."""

    record: UsageRecord
    day: str
    cost_usd: float | None
    price_version: str | None
    unpriced: bool


@dataclass(frozen=True)
class StoredUsage:
    """One ``usage_requests`` row, as read back."""

    id: int
    record: UsageRecord
    cost_usd: float | None
    price_version: str | None
    unpriced: bool


@dataclass(frozen=True)
class DailyUsage:
    """One ``usage_daily`` rollup row. A grouping field is ``None`` for "none"."""

    day: str
    agent_uid: str | None
    agent_type: str | None
    connection_uid: str | None
    model: str | None
    requests: int = 0
    unknown_requests: int = 0
    unpriced_requests: int = 0
    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_search_requests: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class RequestFilters:
    """Narrowing of the per-request list; ``None`` means any."""

    agent_uid: str | None = None
    connection_uid: str | None = None
    model: str | None = None
    since: datetime | None = None
    until: datetime | None = None

    def fingerprint(self) -> dict[str, Any]:
        return {
            "agent_uid": self.agent_uid,
            "connection_uid": self.connection_uid,
            "model": self.model,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
        }


@dataclass(frozen=True)
class SpoolBatch:
    """The parsed lines of one spool file; ``malformed`` lines were skipped."""

    records: list[UsageRecord]
    malformed: int


# -- ports ---------------------------------------------------------------------


class UsageRepo(Protocol):
    async def ingest(self, rows: Sequence[PricedRecord]) -> int:
        """Insert each row not already present (by ``source`` + ``dedupe_key``)
        and add exactly those to the daily rollup, all in ONE transaction.
        Returns how many rows were new."""
        ...

    async def daily(self, start_day: str, end_day: str) -> list[DailyUsage]:
        """Rollup rows for local days ``start_day`` … ``end_day`` inclusive."""
        ...

    async def requests(
        self,
        *,
        filters: RequestFilters,
        limit: int,
        after: tuple[datetime, int] | None,
    ) -> list[StoredUsage]:
        """Detail rows newest first (``started_at`` desc, ``id`` desc),
        strictly after ``after`` in that order."""
        ...


class SpoolReader(Protocol):
    def completed(self) -> list[Path]:
        """Completed spool files, oldest first (never a ``.jsonl.part``)."""
        ...

    def read(self, path: Path) -> SpoolBatch: ...

    def delete(self, path: Path) -> None: ...


class ConnectionPriceLookup(Protocol):
    async def resolve_price(
        self, connection_uid: str | None, model: str | None, at: datetime
    ) -> ResolvedPrice | None:
        """The price a request for ``model`` through ``connection_uid`` at
        ``at`` is costed at, and where it came from; ``None`` when nothing
        prices it (spec provider-switching "Resolve each model's price from
        the provider, its API, or the bundled list")."""
        ...


class ConnectionNames(Protocol):
    async def names(self, uids: Iterable[str]) -> Mapping[str, str]:
        """Current display names of those connections that still exist."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """The wall clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


__all__ = [
    "Clock",
    "ConnectionNames",
    "ConnectionPriceLookup",
    "DailyUsage",
    "PricedRecord",
    "RequestFilters",
    "SpoolBatch",
    "SpoolReader",
    "StoredUsage",
    "SystemClock",
    "UsageRepo",
]
