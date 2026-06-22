"""Provider introspection: test a connection + list a provider's models.

The application service resolves a Coffer credential ref to a secret and
delegates the actual outbound call to a ``ProviderIntrospectionPort`` (an
infrastructure adapter — the OpenAI-compatible client + SSRF guard live there,
per the engine-confinement and application-no-infrastructure contracts).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

#: Providers Coffer treats as machine-local; their base URL is loopback, so the
#: SSRF guard (which blocks loopback) is intentionally skipped for them.
LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "local"})


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelList:
    models: list[str]
    message: str = ""


class ProviderIntrospectionPort(Protocol):
    """Outbound provider calls (infrastructure implements this)."""

    async def list_models(
        self, *, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str]: ...

    async def test_chat(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> None:
        """Raise on failure (any exception); return None on success."""

    async def test_embedding(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> int:
        """Return the embedding dimension; raise on failure."""


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
        return ModelList(models=models)

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

    async def test_embedding(
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
            dim = await self._port.test_embedding(
                provider=provider, model=model, base_url=base_url, api_key=key
            )
        except Exception as e:
            return TestResult(ok=False, message=str(e))
        return TestResult(
            ok=True, message=f"returned {dim}-dimensional embeddings", detail={"dimensions": dim}
        )
