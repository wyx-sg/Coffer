"""What the usage meter asks the provider kind (spec provider-switching "Price
usage from a bundled snapshot and per-connection prices", "Report usage by
model, agent or day over a range"): a connection's own price for a model, and
the names the usage report shows beside connection uids. Satisfies the usage
application's ``ConnectionPriceLookup`` and ``ConnectionNames`` ports, wired at
the composition root."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from coffer.domain.usage.pricing import ModelPrice

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class ProviderUsageLookup:
    def __init__(self, service: ProviderService) -> None:
        self._service = service

    async def override_price(
        self, connection_uid: str | None, model: str | None
    ) -> ModelPrice | None:
        if not connection_uid or not model:
            return None
        try:
            resource = await self._service.get(connection_uid)
        except Exception:
            return None
        curated = self._service._cfg(resource).curated(model)
        if curated is None or curated.price is None:
            return None
        p = curated.price
        return ModelPrice(
            input=p.input,
            output=p.output,
            cache_write_5m=p.cache_write_5m,
            cache_write_1h=p.cache_write_1h,
            cache_read=p.cache_read,
            web_search=p.web_search,
        )

    async def names(self, uids: Iterable[str]) -> dict[str, str]:
        wanted = set(uids)
        return {r.uid: r.name for r in await self._service.list() if r.uid in wanted}


__all__ = ["ProviderUsageLookup"]
