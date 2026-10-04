"""What the usage meter asks the provider kind (spec provider-switching
"Resolve each model's price from the provider, its API, or the bundled list",
"Report usage by model, agent or day over a range"): the price a request is
costed at and the names the usage report shows beside connection uids.
Satisfies the usage application's ``ConnectionPriceLookup`` and
``ConnectionNames`` ports, wired at the composition root."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.provider.prices import ProviderPriceResolver
from coffer.domain.usage.pricing import ResolvedPrice

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class ProviderUsageLookup:
    def __init__(self, service: ProviderService, resolver: ProviderPriceResolver) -> None:
        self._service = service
        self._resolver = resolver

    async def resolve_price(
        self, connection_uid: str | None, model: str | None, at: datetime
    ) -> ResolvedPrice | None:
        return await self._resolver.resolve(connection_uid, model, at)

    async def names(self, uids: Iterable[str]) -> dict[str, str]:
        wanted = set(uids)
        return {r.uid: r.name for r in await self._service.list() if r.uid in wanted}


__all__ = ["ProviderUsageLookup"]
