"""Ingest the model proxy's usage spool into the database (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

The proxy never opens the database; it spools records into JSON-lines files and
the daemon — the only writer — ingests them here. Per completed file:

1. parse its lines (a malformed line is logged and skipped, never fatal);
2. price each record: the connection's own override first, else the bundled
   snapshot; the version used is stored with the row, and a model neither
   covers is flagged unpriced (never priced at zero); a record whose usage is
   unknown carries no cost at all;
3. write the detail rows and their daily rollup in ONE transaction, the rollup
   counting only the rows that were new — so a file ingested twice (a crash
   between commit and delete) writes nothing twice;
4. delete the file, only after that commit.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, tzinfo

from coffer.application.usage.ports import (
    ConnectionPriceLookup,
    PricedRecord,
    SpoolReader,
    UsageRepo,
)
from coffer.domain.usage.pricing import (
    BUNDLED_SNAPSHOT,
    PriceSnapshot,
    TokenCounts,
    estimate_cost,
    override_label,
)
from coffer.domain.usage.ranges import local_day
from coffer.domain.usage.records import UsageRecord

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    """What one pass did."""

    files: int = 0
    inserted: int = 0
    duplicates: int = 0
    malformed: int = 0


def local_tz() -> tzinfo:
    """This machine's local time zone."""
    tz = datetime.now().astimezone().tzinfo
    assert tz is not None
    return tz


class UsageIngestService:
    """Moves completed spool files into ``usage_requests`` + ``usage_daily``."""

    def __init__(
        self,
        *,
        repo: UsageRepo,
        spool: SpoolReader,
        prices: ConnectionPriceLookup,
        snapshot: PriceSnapshot = BUNDLED_SNAPSHOT,
        tz: tzinfo | None = None,
    ) -> None:
        self._repo = repo
        self._spool = spool
        self._prices = prices
        self._snapshot = snapshot
        # The rollup is keyed by the LOCAL day an attempt started on, so the
        # Usage page's "today" is the user's today.
        self._tz = tz or local_tz()
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()

    async def price(self, record: UsageRecord) -> PricedRecord:
        """``record`` with its estimated cost and the price version used."""
        day = local_day(record.started_at, self._tz)
        if not record.usage_known:
            return PricedRecord(record, day, cost_usd=None, price_version=None, unpriced=False)
        tokens = TokenCounts.of(record)
        try:
            override = await self._prices.override_price(record.connection_uid, record.model)
        except Exception:
            _logger.warning("usage.ingest.override_lookup_failed", exc_info=True)
            override = None
        if override is not None and record.connection_uid:
            cost = estimate_cost(tokens, override)
            return PricedRecord(record, day, cost, override_label(record.connection_uid), False)
        price = self._snapshot.lookup(record.model)
        if price is None:
            return PricedRecord(record, day, cost_usd=None, price_version=None, unpriced=True)
        return PricedRecord(record, day, estimate_cost(tokens, price), self._snapshot.label, False)

    async def ingest_once(self) -> IngestResult:
        """Ingest every completed spool file present now."""
        async with self._lock:
            files = inserted = duplicates = malformed = 0
            for path in self._spool.completed():
                try:
                    batch = self._spool.read(path)
                except OSError:
                    _logger.warning("usage.ingest.read_failed", extra={"file": str(path)})
                    continue
                if batch.malformed:
                    _logger.warning(
                        "usage.ingest.malformed_lines",
                        extra={"file": str(path), "lines": batch.malformed},
                    )
                rows = [await self.price(r) for r in batch.records]
                new = await self._repo.ingest(rows) if rows else 0
                # Only now — the rows are committed — may the file go.
                try:
                    self._spool.delete(path)
                except OSError:
                    _logger.warning("usage.ingest.delete_failed", extra={"file": str(path)})
                files += 1
                inserted += new
                duplicates += len(rows) - new
                malformed += batch.malformed
            return IngestResult(files, inserted, duplicates, malformed)

    async def run(self, interval: float) -> None:
        """Ingest every ``interval`` seconds until :meth:`stop`."""
        self._stop.clear()
        while not self._stop.is_set():
            try:
                await self.ingest_once()
            except Exception:
                _logger.exception("usage.ingest.pass_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval)

    def stop(self) -> None:
        self._stop.set()


__all__ = ["IngestResult", "UsageIngestService", "local_tz"]
