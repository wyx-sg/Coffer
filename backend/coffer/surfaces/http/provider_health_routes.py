"""/api/v1/providers/health — each connection's kept health verdict, and a
re-check of one (spec provider-switching "Know each connection's health without
opening it").

GET answers what this machine last saw for every connection that has a
verdict, read from the store — it calls no endpoint. POST
``/{uid}/check`` lists that connection's models now (no token is spent),
keeps the verdict and answers it; it is the Overview's in-place action for an
unreachable connection. Registered before the provider router, whose
``/{uid}`` would otherwise answer ``health`` as a uid.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from coffer.application.provider.health import ProviderHealthService
from coffer.domain.provider.health import HealthSource, HealthStatus, ProviderHealth
from coffer.surfaces.http.auth import require_token

router = APIRouter(
    prefix="/api/v1/providers",
    tags=["providers"],
    dependencies=[Depends(require_token)],
)

_service: ProviderHealthService | None = None


def set_provider_health_service(service: ProviderHealthService | None) -> None:
    """Called by the composition root once on startup."""
    global _service
    _service = service


def get_provider_health_service_optional() -> ProviderHealthService | None:
    return _service


def get_provider_health_service() -> ProviderHealthService:
    if _service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="provider health not wired"
        )
    return _service


class ProviderHealthOut(BaseModel):
    """One connection's last verdict: does its endpoint answer, and take its key."""

    uid: str
    status: HealthStatus
    #: When the verdict was made.
    checked_at: datetime
    #: When this status was first seen without a break.
    since: datetime
    #: ``check`` (a model listing Coffer made) or ``request`` (an agent's real call).
    source: HealthSource
    #: Why it failed; empty when reachable.
    message: str


class ProviderHealthListOut(BaseModel):
    """Every connection that has a verdict; one without has never been checked."""

    connections: list[ProviderHealthOut]


class ProviderCheckOut(BaseModel):
    """What a check found; ``health`` is ``None`` when nothing was checked (the
    connection's key waits for approval, or it is a retired connection)."""

    health: ProviderHealthOut | None


def health_out(uid: str, health: ProviderHealth) -> ProviderHealthOut:
    return ProviderHealthOut(
        uid=uid,
        status=health.status,
        checked_at=health.checked_at,
        since=health.started,
        source=health.source,
        message=health.message,
    )


@router.get("/health", response_model=ProviderHealthListOut)
async def list_provider_health(
    svc: ProviderHealthService = Depends(get_provider_health_service),  # noqa: B008
) -> ProviderHealthListOut:
    """Each connection's kept verdict; touches no endpoint."""
    verdicts = await svc.all()
    return ProviderHealthListOut(
        connections=[health_out(uid, h) for uid, h in sorted(verdicts.items())]
    )


@router.post("/{uid}/check", response_model=ProviderCheckOut)
async def check_provider(
    uid: str,
    svc: ProviderHealthService = Depends(get_provider_health_service),  # noqa: B008
) -> ProviderCheckOut:
    """List ``uid``'s models now and keep the verdict (404 for no such connection)."""
    health = await svc.check(uid)
    if health is None:
        return ProviderCheckOut(health=None)
    kept = await svc.get(uid)
    return ProviderCheckOut(health=health_out(uid, kept or health))


__all__ = [
    "ProviderCheckOut",
    "ProviderHealthListOut",
    "ProviderHealthOut",
    "get_provider_health_service",
    "get_provider_health_service_optional",
    "health_out",
    "router",
    "set_provider_health_service",
]
