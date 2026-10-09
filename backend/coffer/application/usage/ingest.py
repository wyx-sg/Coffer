"""Ingest the model proxy's usage spool into the database (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

The proxy never opens the database; it spools records into JSON-lines files and
the daemon — the only writer — ingests them here. Per completed file:

1. parse its lines (a malformed line is logged and skipped, never fatal);
2. price each record at the price the provider kind resolves for its
   connection and model (you set → local → from the provider's API → bundled;
   spec provider-switching "Resolve each model's price from the provider, its
   API, or the bundled list"); the label of the price used is stored with the
   row, and a model nothing prices is flagged unpriced (never priced at zero);
   a record whose usage is unknown carries no cost at all;
3. write the detail rows and their daily rollup in ONE transaction, the rollup
   counting only the rows that were new — so a file ingested twice (a crash
   between commit and delete) writes nothing twice;
4. delete the file, only after that commit;
5. hand the file's records to :attr:`UsageIngestService.observe` when one is
   set — the provider kind reads what each request says about its
   connection's health from them (spec provider-switching "Know each
   connection's health without opening it").
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo

from coffer.application.usage.ports import (
    ConnectionPriceLookup,
    PricedRecord,
    SpoolReader,
    UsageRepo,
)
from coffer.domain.usage.pricing import TokenCounts, estimate_cost
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
        tz: tzinfo | None = None,
    ) -> None:
        self._repo = repo
        self._spool = spool
        self._prices = prices
        # The rollup is keyed by the LOCAL day a request started on, so the
        # Usage page's "today" is the user's today.
        self._tz = tz or local_tz()
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        #: Told every ingested file's records, after their commit.
        self.observe: Callable[[Sequence[UsageRecord]], Awaitable[None]] | None = None

    async def price(self, record: UsageRecord) -> PricedRecord:
        """``record`` with its estimated cost and the label of the price used."""
        day = local_day(record.started_at, self._tz)
        if not record.usage_known:
            return PricedRecord(record, day, cost_usd=None, price_version=None, unpriced=False)
        try:
            resolved = await self._prices.resolve_price(
                record.connection_uid, record.model, record.started_at
            )
        except Exception:
            _logger.warning("usage.ingest.price_lookup_failed", exc_info=True)
            resolved = None
        if resolved is None:
            return PricedRecord(record, day, cost_usd=None, price_version=None, unpriced=True)
        cost = estimate_cost(TokenCounts.of(record), resolved.price)
        return PricedRecord(record, day, cost, resolved.label, False)

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
                if self.observe is not None and batch.records:
                    try:
                        await self.observe(batch.records)
                    except Exception:
                        _logger.warning("usage.ingest.observe_failed", exc_info=True)
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
