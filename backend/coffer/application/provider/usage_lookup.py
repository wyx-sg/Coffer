"""What the usage meter asks the provider kind (spec provider-switching
"Resolve each model's price from the provider, its API, or the bundled list",
"Report usage by model, agent or day over a range", "Log every failover in
Activity"): the price a request is costed at, the names the usage report shows
beside connection uids, and where a failover is recorded. Satisfies the usage
application's ``ConnectionPriceLookup``, ``ConnectionNames`` and
``FailoverLog`` ports, wired at the composition root."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.usage.ports import FailoverEvent
from coffer.domain.audit import AuditEventType
from coffer.domain.usage.pricing import ResolvedPrice

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class ProviderUsageLookup:
    def __init__(
        self,
        service: ProviderService,
        resolver: ProviderPriceResolver,
        audit: AuditService | None = None,
    ) -> None:
        self._service = service
        self._resolver = resolver
        self._audit = audit

    async def resolve_price(
        self, connection_uid: str | None, model: str | None, at: datetime
    ) -> ResolvedPrice | None:
        return await self._resolver.resolve(connection_uid, model, at)

    async def names(self, uids: Iterable[str]) -> dict[str, str]:
        wanted = set(uids)
        return {r.uid: r.name for r in await self._service.list() if r.uid in wanted}

    async def failed_over(self, event: FailoverEvent) -> None:
        """One Activity row per failover, filed against the connection the
        request left, so it also reads in that provider's own history."""
        if self._audit is None:
            return
        resource = None
        if event.from_uid:
            try:
                resource = await self._service.get(event.from_uid)
            except Exception:
                resource = None
        await self._audit.record(
            AuditEventType.PROVIDER_FAILOVER.value,
            resource=resource,
            actor="model-proxy",
            details={
                "at": event.at.isoformat(),
                "agent_uid": event.agent_uid,
                "agent_type": event.agent_type,
                "model": event.model,
                "from": event.from_name,
                "from_uid": event.from_uid,
                "to": event.to_name,
                "to_uid": event.to_uid,
                "reason": event.reason,
            },
        )


__all__ = ["ProviderUsageLookup"]
