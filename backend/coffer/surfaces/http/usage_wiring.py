"""Composition of the usage kind (ADR usage-is-metered-at-the-proxy-and-
subscriptions-show-only-official-quota).

:func:`wire_usage` builds the ingest and query services over the SQLAlchemy
repo and the spool reader, publishes the route dependencies, and returns a
:class:`UsageWiring` whose ``start()`` / ``stop()`` the lifespan drives: the
spool ingest every 2 seconds.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.provider.service import ProviderService
from coffer.application.provider.usage_lookup import ProviderUsageLookup
from coffer.application.retention_registry import PrunableRegistry, PrunableTable
from coffer.application.runtime.supervisor import spawn
from coffer.application.usage.ingest import UsageIngestService
from coffer.application.usage.ports import (
    ConnectionNames,
    ConnectionPriceLookup,
    FailoverLog,
)
from coffer.application.usage.query import UsageQueryService
from coffer.infrastructure.persistence.usage_repo import SqlAlchemyUsageRepo
from coffer.infrastructure.usage.spool_reader import FileSpoolReader
from coffer.surfaces.http.usage_dependencies import set_usage_query_service

_logger = logging.getLogger(__name__)

#: How often the daemon empties the proxy's spool.
INGEST_INTERVAL_SECONDS = 2.0


@dataclass
class UsageWiring:
    """The usage kind's services and its ingest loop."""

    ingest: UsageIngestService
    query: UsageQueryService
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    async def start(self) -> None:
        """Start the ingest loop (idempotent)."""
        if self._tasks:
            return
        self._tasks = [spawn(self.ingest.run(INGEST_INTERVAL_SECONDS), name="usage-ingest")]

    async def stop(self) -> None:
        """Stop the loop; a final ingest pass drains what the spool holds."""
        self.ingest.stop()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            except Exception:
                _logger.warning("usage.loop_stop_failed", exc_info=True)
        try:
            await self.ingest.ingest_once()
        except Exception:
            _logger.warning("usage.final_ingest_failed", exc_info=True)


def wire_usage(
    sm: async_sessionmaker[AsyncSession],
    *,
    price_lookup: ConnectionPriceLookup,
    connection_names: ConnectionNames,
    failovers: FailoverLog | None = None,
    spool_dir: Path | None = None,
    is_enabled: Callable[[], bool] = lambda: True,
) -> UsageWiring:
    """Build the usage services and publish the ``/api/v1/usage`` dependencies."""
    usage_repo = SqlAlchemyUsageRepo(sm)
    ingest = UsageIngestService(
        repo=usage_repo,
        spool=FileSpoolReader(spool_dir),
        prices=price_lookup,
        failovers=failovers,
        is_enabled=is_enabled,
    )
    query = UsageQueryService(repo=usage_repo, connection_names=connection_names)
    set_usage_query_service(query)
    return UsageWiring(ingest=ingest, query=query)


async def wire_model_usage(
    sm: async_sessionmaker[AsyncSession],
    provider_svc: ProviderService,
    *,
    prices: ProviderPriceResolver,
    audit: AuditService,
    is_enabled: Callable[[], bool] = lambda: True,
) -> UsageWiring:
    """The composition the lifespan uses: prices and names from the provider
    kind, failovers filed in the audit log, and the ingest loop started.
    ``is_enabled`` is whether the ``models`` feature is on: the loop skips its
    passes while it is off (spec experimental-features "Close every surface of
    a switched-off feature")."""
    lookup = ProviderUsageLookup(provider_svc, prices, audit)
    wiring = wire_usage(
        sm,
        price_lookup=lookup,
        connection_names=lookup,
        failovers=lookup,
        is_enabled=is_enabled,
    )
    await wiring.start()
    return wiring


def register_usage_retention(registry: PrunableRegistry) -> None:
    """File the usage tables with the retention registry — the usage feature's
    own registration, kept with its wiring rather than in the MCP composition.

    Usage metering (ADR usage-is-metered-at-the-proxy-and-subscriptions-show-
    only-official-quota): the per-request detail is a run log like the MCP
    calls and follows THEIR window rather than growing a setting of its own;
    the daily rollup the Usage page charts is kept for a year. The rollup's
    ``day`` is a local ``YYYY-MM-DD`` string, which compares against the
    cutoff instant as text — to the day, which is the rollup's resolution.
    """
    registry.register(
        PrunableTable(
            name="usage_requests",
            timestamp_column="started_at",
            default_retention_days=None,
            display_name="Usage Requests",
            description="Per-request model usage recorded by the model proxy.",
            policy_name="mcp_invocations",
        )
    )
    registry.register(
        PrunableTable(
            name="usage_daily",
            timestamp_column="day",
            default_retention_days=365,
            display_name="Daily Usage",
            description="Daily model usage and estimated cost per agent, connection and model.",
        )
    )


__all__ = [
    "INGEST_INTERVAL_SECONDS",
    "UsageWiring",
    "register_usage_retention",
    "wire_model_usage",
    "wire_usage",
]
