"""Resolves a provider model's context window on a connection (spec
provider-switching "Resolve each provider model's context window").

The order is :func:`~coffer.domain.provider.model_window.resolve_window`'s;
this adds the bundled list, read from whichever copy is fresher right now
(never the network), and the connection lookup the Models section needs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.model_window import ResolvedWindow, resolve_window
from coffer.domain.usage.bundled_prices import BundledPrices

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


class ProviderWindowResolver:
    """You set → the endpoint's → the bundled list's → unknown."""

    def __init__(
        self,
        bundled: BundledPrices | Callable[[], BundledPrices],
        service: ProviderService | None = None,
    ) -> None:
        self._bundled: Callable[[], BundledPrices] = (
            bundled if callable(bundled) else (lambda: bundled)
        )
        self._service = service

    def attach(self, service: ProviderService) -> None:
        """Hand over the connection service once it exists — it is built with
        this resolver's :meth:`tokens`, so it cannot be passed in first."""
        self._service = service

    def for_config(self, cfg: ProviderConfig, model: str) -> ResolvedWindow | None:
        return resolve_window(
            cfg.curated(model),
            lambda: self._bundled().context_window(model, base_url=cfg.base_url),
        )

    def tokens(self, cfg: ProviderConfig, model: str) -> int | None:
        """A ``WindowOf`` — what the projection is handed."""
        found = self.for_config(cfg, model)
        return found.tokens if found is not None else None

    async def resolve_many(
        self, connection_uid: str, models: Iterable[str]
    ) -> dict[str, ResolvedWindow | None]:
        """Each of ``models`` on one connection — for the Models section."""
        if self._service is None:
            return dict.fromkeys(models)
        cfg = self._service._cfg(await self._service.get(connection_uid))
        return {m: self.for_config(cfg, m) for m in dict.fromkeys(models)}


__all__ = ["ProviderWindowResolver"]
