"""Provider introspection: test a connection + list a provider's models.

The service resolves a Coffer secret ref to a secret and delegates the
actual outbound call to the ``ProviderIntrospectionPort`` declared in
``application.provider.ports``; the adapter behind it is
``infrastructure.provider.introspector``.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.provider.ports import (
    DiscoveredModel,
    ListedModel,
    ModelList,
    ProviderIntrospectionPort,
    ReportedPriceStore,
    TestResult,
)
from coffer.domain.model_proxy.state import upstream_root
from coffer.domain.provider.modality import infer_modality


class ModelIntrospectionService:
    """Resolves a secret ref then drives the introspection port.

    A failed test is returned as ``TestResult(ok=False, ...)`` (not raised) so
    the surface can answer 200 with a humanized message, mirroring how mature
    clients surface connection checks.
    """

    def __init__(
        self,
        port: ProviderIntrospectionPort,
        resolve_secret: Callable[[str], str],
        reported_prices: ReportedPriceStore | None = None,
        default_base_url: Callable[[str], str | None] | None = None,
    ) -> None:
        self._port = port
        self._resolve = resolve_secret
        # Where the prices an endpoint's API reports are remembered, so usage
        # is costed from them without asking the endpoint per request.
        self._reported = reported_prices
        self._default_base_url = default_base_url or (lambda _provider: None)

    def _key_for(
        self, provider: str, secret_ref: str | None, secret_value: str | None = None
    ) -> str | None:
        # An inline (not-yet-saved) secret wins so the connection dialog can
        # test/fetch before the secret ref exists; otherwise resolve the ref.
        if secret_value:
            return secret_value
        if secret_ref:
            return self._resolve(secret_ref)
        return None

    async def list_models(
        self,
        *,
        provider: str,
        base_url: str | None,
        secret_ref: str | None,
        secret_value: str | None = None,
    ) -> ModelList:
        try:
            key = self._key_for(provider, secret_ref, secret_value)
            listed = await self._port.list_models(provider=provider, base_url=base_url, api_key=key)
        except Exception as e:  # degrade to an empty list + reason — never 500 the picker
            return ModelList(models=[], message=str(e), reachable=False)
        entries = [m if isinstance(m, ListedModel) else ListedModel(id=m) for m in listed]
        self._remember_prices(provider, base_url, entries)
        if not entries:
            # Say what happened, nothing more: no surface takes a typed model id
            # (spec provider-switching "Choose a model from a fixed list").
            return ModelList(models=[], message="the endpoint listed no models")
        return ModelList(
            models=[
                DiscoveredModel(
                    id=m.id, modality=infer_modality(m.id), context_window=m.context_window
                )
                for m in entries
            ]
        )

    def _remember_prices(
        self, provider: str, base_url: str | None, entries: list[ListedModel]
    ) -> None:
        """Keep what the endpoint's API reported its models cost — only when it
        reported something, so an endpoint that says nothing about price
        never erases what an earlier listing learned."""
        if self._reported is None:
            return
        prices = {m.id: m.price for m in entries if m.price is not None}
        url = base_url or self._default_base_url(provider)
        if not prices or not url:
            return
        try:
            self._reported.put(upstream_root(url), prices)
        except Exception:  # a derived cache: failing to write it costs nothing now
            return

    async def test_connection(
        self,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        secret_ref: str | None,
        secret_value: str | None = None,
    ) -> TestResult:
        try:
            key = self._key_for(provider, secret_ref, secret_value)
            await self._port.test_chat(
                provider=provider, model=model, base_url=base_url, api_key=key
            )
        except Exception as e:
            return TestResult(ok=False, message=str(e))
        return TestResult(ok=True, message="connection ok")
