"""Where a model's price on a provider comes from (spec provider-switching
"Resolve each model's price from the provider, its API, or the bundled list").

One order, used by the usage meter when it costs a request and by the Models
section when it shows a price, so the two never disagree:

1. **You set** — the price the user recorded on the provider for that model;
2. **local** — a model runtime on this machine costs nothing;
3. **From <provider>** — what the provider's own API reported when its models
   were last listed (OpenRouter and gateways like it), kept in a derived store;
4. **Bundled** — the price list shipped with the release, scoped to the
   provider the endpoint belongs to;
5. otherwise unpriced (``None``): shown as "—", never as zero.

Subscription logins never reach this: they are not metered, and show only
their official quota.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.provider.ports import ReportedPriceStore
from coffer.domain.model_proxy.state import upstream_root
from coffer.domain.provider.config import CuratedPrice, ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.usage.bundled_prices import BundledPrices
from coffer.domain.usage.pricing import (
    FREE,
    LOCAL_LABEL,
    ModelPrice,
    PriceSource,
    ResolvedPrice,
    override_label,
    reported_label,
)

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


def curated_price(price: CuratedPrice) -> ModelPrice:
    """A user's price on a provider as the meter's price."""
    return ModelPrice(
        input=price.input,
        output=price.output,
        cache_write_5m=price.cache_write_5m,
        cache_write_1h=price.cache_write_1h,
        cache_read=price.cache_read,
        web_search=price.web_search,
    )


class ProviderPriceResolver:
    """Resolves a model's price on a connection, and names where it came from."""

    def __init__(
        self,
        service: ProviderService,
        bundled: BundledPrices | Callable[[], BundledPrices],
        reported: ReportedPriceStore | None = None,
    ) -> None:
        self._service = service
        # A callable when the daily refresh may swap the list under us: each
        # lookup reads whichever list is fresher right now, never the network.
        self._bundled: Callable[[], BundledPrices] = (
            bundled if callable(bundled) else (lambda: bundled)
        )
        self._reported = reported

    @property
    def bundled_version(self) -> str:
        return self._bundled().version

    def for_config(
        self,
        resource: Resource | None,
        cfg: ProviderConfig | None,
        model: str,
        *,
        at: datetime | None = None,
    ) -> ResolvedPrice | None:
        """The price of ``model`` on this connection (or, with none, by the
        model alone from the bundled list)."""
        if resource is not None and cfg is not None:
            curated = cfg.curated(model)
            if curated is not None and curated.price is not None:
                return ResolvedPrice(
                    curated_price(curated.price), PriceSource.USER, override_label(resource.uid)
                )
            if cfg.is_local:
                return ResolvedPrice(FREE, PriceSource.LOCAL, LOCAL_LABEL)
            if self._reported is not None:
                reported = self._reported.get(upstream_root(cfg.base_url))
                price = reported.prices.get(model) if reported is not None else None
                if price is not None:
                    return ResolvedPrice(
                        price, PriceSource.PROVIDER, reported_label(resource.uid), resource.name
                    )
        bundled = self._bundled()
        found = bundled.lookup(model, base_url=cfg.base_url if cfg else None, at=at)
        if found is None:
            return None
        return ResolvedPrice(
            found.price,
            PriceSource.BUNDLED,
            bundled.label,
            found.provider_name,
            bundled.updated,
        )

    async def _connection(self, uid: str | None) -> tuple[Resource | None, ProviderConfig | None]:
        if not uid:
            return None, None
        try:
            resource = await self._service.get(uid)
            return resource, self._service._cfg(resource)
        except Exception:
            return None, None

    async def resolve(
        self, connection_uid: str | None, model: str | None, at: datetime | None = None
    ) -> ResolvedPrice | None:
        """The price a request for ``model`` through ``connection_uid`` is costed at."""
        if not model:
            return None
        resource, cfg = await self._connection(connection_uid)
        return self.for_config(resource, cfg, model, at=at)

    async def resolve_many(
        self, connection_uid: str, models: Iterable[str]
    ) -> dict[str, ResolvedPrice | None]:
        """Each of ``models`` on one connection, now — for the Models section."""
        resource, cfg = await self._connection(connection_uid)
        return {m: self.for_config(resource, cfg, m) for m in dict.fromkeys(models)}


__all__ = ["ProviderPriceResolver", "curated_price"]
