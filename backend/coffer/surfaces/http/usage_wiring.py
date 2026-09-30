"""Composition of the usage kind (ADR usage-is-metered-at-the-proxy-and-
subscriptions-show-only-official-quota).

:func:`wire_usage` builds the ingest, query and quota services over the
SQLAlchemy repos and the spool reader, publishes the route dependencies, and
returns a :class:`UsageWiring` whose ``start()`` / ``stop()`` the lifespan
drives: the spool ingest every 2 seconds and the Codex quota read every five
minutes (the quota service itself enforces that floor). The chat kind's quota
observer is ``wiring.quota.observe_agent_event``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.provider.service import ProviderService
from coffer.application.provider.usage_lookup import ProviderUsageLookup
from coffer.application.usage.ingest import UsageIngestService
from coffer.application.usage.ports import (
    CodexRateLimitReader,
    ConnectionNames,
    ConnectionPriceLookup,
    FailoverLog,
)
from coffer.application.usage.query import UsageQueryService
from coffer.application.usage.quota import BACKGROUND_INTERVAL, QuotaService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.chat.codex_rate_limits import AppServerRateLimitReader
from coffer.infrastructure.persistence.usage_repo import (
    SqlAlchemyQuotaRepo,
    SqlAlchemyUsageRepo,
)
from coffer.infrastructure.usage.spool_reader import FileSpoolReader
from coffer.surfaces.http.chat_provider_wiring import agent_home_env_resolver
from coffer.surfaces.http.usage_dependencies import (
    set_quota_service,
    set_usage_query_service,
)

_logger = logging.getLogger(__name__)

#: How often the daemon empties the proxy's spool.
INGEST_INTERVAL_SECONDS = 2.0


@dataclass
class UsageWiring:
    """The usage kind's services and its two background loops."""

    ingest: UsageIngestService
    query: UsageQueryService
    quota: QuotaService
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    async def start(self) -> None:
        """Start the ingest loop and the Codex quota loop (idempotent)."""
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self.ingest.run(INGEST_INTERVAL_SECONDS), name="usage-ingest"),
            asyncio.create_task(
                self.quota.run(BACKGROUND_INTERVAL.total_seconds()), name="usage-quota"
            ),
        ]

    async def stop(self) -> None:
        """Stop both loops; a final ingest pass drains what the spool holds."""
        self.ingest.stop()
        self.quota.stop()
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
    codex_reader: CodexRateLimitReader | None,
    spool_dir: Path | None = None,
    quota_background_enabled: Callable[[], Awaitable[bool]] | None = None,
) -> UsageWiring:
    """Build the usage services and publish the ``/api/v1/usage`` dependencies.

    ``codex_reader`` ``None`` means Codex quota is only ever pushed (by live
    chat turns), never pulled. ``quota_background_enabled`` gates the
    five-minute background read (``None`` ⇒ always, while a reader exists);
    a manual refresh is never gated by it.
    """
    usage_repo = SqlAlchemyUsageRepo(sm)
    ingest = UsageIngestService(
        repo=usage_repo,
        spool=FileSpoolReader(spool_dir),
        prices=price_lookup,
        failovers=failovers,
    )
    query = UsageQueryService(repo=usage_repo, connection_names=connection_names)
    quota = QuotaService(
        repo=SqlAlchemyQuotaRepo(sm),
        codex_reader=codex_reader,
        background_enabled=quota_background_enabled,
    )
    set_usage_query_service(query)
    set_quota_service(quota)
    return UsageWiring(ingest=ingest, query=query, quota=quota)


#: The agent type ``codex app-server`` answers the quota of.
_CODEX_READER_AGENT = "codex"

#: Set to ``off`` to never pull Codex's quota in the background (the test
#: suite sets it: a pull spawns ``codex app-server``).
QUOTA_POLL_ENV = "COFFER_QUOTA_POLL"


async def wire_model_usage(
    sm: async_sessionmaker[AsyncSession],
    provider_svc: ProviderService,
    agents: AgentService,
    *,
    prices: ProviderPriceResolver,
    audit: AuditService,
) -> UsageWiring:
    """The composition the lifespan uses: prices and names from the provider
    kind, Codex's quota read from a short-lived ``codex app-server`` under the
    agent's own home — in the background only while a Codex agent is on its
    own (subscription) login, since an agent on a connection has no quota to
    show — failovers filed in the audit log, and both loops started."""
    lookup = ProviderUsageLookup(provider_svc, prices, audit)
    # The agent whose quota the reader pulls: the one ``codex app-server`` is.
    codex_type = AgentType(_CODEX_READER_AGENT)

    async def codex_on_its_own_login() -> bool:
        if os.environ.get(QUOTA_POLL_ENV, "").lower() == "off":
            return False
        rows = [a for a in await agents.list() if a.enabled]
        codex = [a for a in rows if AgentConfig.model_validate(a.config).type is codex_type]
        if not codex:
            return False
        for conn in await provider_svc.list():
            cfg = provider_svc._cfg(conn)
            if cfg.is_active and codex_type in provider_svc._compat(conn, rows):
                return False
        return True

    wiring = wire_usage(
        sm,
        price_lookup=lookup,
        connection_names=lookup,
        failovers=lookup,
        codex_reader=AppServerRateLimitReader(
            resolve_env=agent_home_env_resolver(_CODEX_READER_AGENT)
        ),
        quota_background_enabled=codex_on_its_own_login,
    )
    await wiring.start()
    return wiring


__all__ = [
    "INGEST_INTERVAL_SECONDS",
    "QUOTA_POLL_ENV",
    "UsageWiring",
    "wire_model_usage",
    "wire_usage",
]
