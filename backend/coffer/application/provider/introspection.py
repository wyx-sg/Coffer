"""Provider introspection: test a connection + list a provider's models.

The service resolves a Coffer credential ref to a secret and delegates the
actual outbound call to the ``ProviderIntrospectionPort`` declared in
``application.provider.ports``; the adapter behind it is
``infrastructure.provider.introspector``.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.provider.ports import (
    DiscoveredModel,
    ModelList,
    ProviderIntrospectionPort,
    TestResult,
)
from coffer.domain.provider.modality import infer_modality


class ModelIntrospectionService:
    """Resolves a credential ref then drives the introspection port.

    A failed test is returned as ``TestResult(ok=False, ...)`` (not raised) so
    the surface can answer 200 with a humanized message, mirroring how mature
    clients surface connection checks.
    """

    def __init__(
        self,
        port: ProviderIntrospectionPort,
        resolve_credential: Callable[[str], str],
    ) -> None:
        self._port = port
        self._resolve = resolve_credential

    def _key_for(
        self, provider: str, credential_ref: str | None, secret_value: str | None = None
    ) -> str | None:
        # An inline (not-yet-saved) secret wins so the connection dialog can
        # test/fetch before the credential ref exists; otherwise resolve the ref.
        if secret_value:
            return secret_value
        if credential_ref:
            return self._resolve(credential_ref)
        return None

    async def list_models(
        self,
        *,
        provider: str,
        base_url: str | None,
        credential_ref: str | None,
        secret_value: str | None = None,
    ) -> ModelList:
        try:
            key = self._key_for(provider, credential_ref, secret_value)
            models = await self._port.list_models(provider=provider, base_url=base_url, api_key=key)
        except Exception as e:  # degrade to manual entry — never 500 the picker
            return ModelList(models=[], message=str(e))
        if not models:
            return ModelList(models=[], message="no models returned; enter a model id manually")
        return ModelList(models=[DiscoveredModel(id=m, modality=infer_modality(m)) for m in models])

    async def test_connection(
        self,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        credential_ref: str | None,
        secret_value: str | None = None,
    ) -> TestResult:
        try:
            key = self._key_for(provider, credential_ref, secret_value)
            await self._port.test_chat(
                provider=provider, model=model, base_url=base_url, api_key=key
            )
        except Exception as e:
            return TestResult(ok=False, message=str(e))
        return TestResult(ok=True, message="connection ok")

    async def detect_protocol(
        self,
        *,
        base_url: str | None,
        credential_ref: str | None,
        secret_value: str | None = None,
    ) -> str:
        # Classify the endpoint's wire so the connection needs no manual type
        # selector (provider switching, D9). Never raises — a failed probe degrades to
        # 'unknown', which the agent page surfaces to all agents (E5).
        try:
            key = self._key_for("", credential_ref, secret_value)
            return await self._port.detect_protocol(base_url=base_url, api_key=key)
        except Exception:
            return "unknown"
