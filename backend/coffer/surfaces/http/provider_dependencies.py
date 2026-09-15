"""FastAPI dependency providers for the provider kind (spec provider-switching).

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely: the connection service, and the introspection service the
connection editors use to probe an endpoint and list its models.
"""

from __future__ import annotations

from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.service import ProviderService

_provider_service: ProviderService | None = None


def set_provider_service(svc: ProviderService) -> None:
    """Called by the composition root once on startup."""
    global _provider_service
    _provider_service = svc


def get_provider_service() -> ProviderService:
    """FastAPI Depends() target."""
    if _provider_service is None:
        raise RuntimeError("provider service not initialised")
    return _provider_service


_introspection_service: ModelIntrospectionService | None = None


def set_introspection_service(svc: ModelIntrospectionService) -> None:
    """Called by the composition root once on startup."""
    global _introspection_service
    _introspection_service = svc


def get_introspection_service() -> ModelIntrospectionService:
    """FastAPI Depends() target."""
    if _introspection_service is None:
        raise RuntimeError("introspection service not initialised")
    return _introspection_service
