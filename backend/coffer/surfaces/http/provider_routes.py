"""/api/v1/providers — provider-profile CRUD + switch (spec provider-switching).

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.provider.service import ProviderService
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedModel, Protocol, ProviderConfig
from coffer.domain.resource import Resource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_provider_service
from coffer.surfaces.http.provider_schemas import (
    ActivateOut,
    ActiveKeyOut,
    DeactivateOut,
    ProviderCreate,
    ProviderListOut,
    ProviderModel,
    ProviderOut,
    ProviderPatch,
    ProviderRename,
)

router = APIRouter(
    prefix="/api/v1/providers",
    tags=["providers"],
    dependencies=[Depends(require_token)],
)


def _curated(models: list[ProviderModel] | None) -> list[CuratedModel] | None:
    """Wire entries → the domain's curated set (``None`` leaves the set alone)."""
    if models is None:
        return None
    return [CuratedModel(id=m.id, modality=m.modality) for m in models]


def _provider_out(resource: Resource) -> ProviderOut:
    cfg = ProviderConfig.model_validate(resource.config)
    return ProviderOut(
        name=resource.name,
        protocol=cfg.protocol,
        base_url=cfg.base_url,
        credential_ref=cfg.credential_ref,
        compatible_agents=[AgentType(a) for a in cfg.resolved_compatible_agents()],
        models=[ProviderModel(id=m.id, modality=m.modality) for m in cfg.models],
        is_active=cfg.is_active,
        internal_default=cfg.internal_default,
        enabled=resource.enabled,
        description=resource.description,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


@router.get("", response_model=ProviderListOut)
async def list_providers(
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ProviderListOut:
    """List all provider profiles."""
    rows = await svc.list()
    return ProviderListOut(providers=[_provider_out(r) for r in rows])


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Create a provider profile (422 when the credential source is invalid)."""
    resource = await svc.create(
        body.name,
        protocol=body.protocol,
        base_url=body.base_url,
        secret_value=body.secret_value,
        credential_ref=body.credential_ref,
        compatible_agents=body.compatible_agents,
        models=_curated(body.models),
        description=body.description,
        actor=actor,
    )
    return _provider_out(resource)


@router.post("/{name}/rename", response_model=ProviderOut)
async def rename_provider(
    name: str,
    body: ProviderRename,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Rename a connection.

    WHY this is its own route and not ``PATCH /{name}``: PATCH edits a
    connection's CONFIG, while the name is its IDENTITY. Renaming repoints the
    owned vault ref, the audit trail and the projected agent config in one
    operation, and a name another connection already uses answers 409 rather
    than being silently merged into that connection the way a patch field would.
    Renaming to the current name is a no-op. 404 when the connection is absent.
    """
    return _provider_out(await svc.rename(name, body.new_name, actor=actor))


@router.get("/active-key/{wire}", response_model=ActiveKeyOut)
async def active_provider_key(
    wire: Protocol,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ActiveKeyOut:
    """Back-compat: the decrypted key of the connection active for ``wire``'s
    agent (legacy ``--wire`` helper). 404 when none. New projections use
    ``GET /{name}/key`` instead, which names the connection directly."""
    return ActiveKeyOut(value=await svc.resolve_active_key(wire))


@router.get("/{name}/key", response_model=ActiveKeyOut)
async def connection_key(
    name: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ActiveKeyOut:
    """The decrypted key of a SPECIFIC connection — what Claude Code's projected
    ``apiKeyHelper`` (``coffer provider key --connection <name>``) fetches, so the
    agent always reads exactly the activated connection's key (no wire+active
    mismatch). 404 when the connection is absent or keyless (ollama)."""
    return ActiveKeyOut(value=await svc.resolve_connection_key(name))


@router.get("/{name}", response_model=ProviderOut)
async def get_provider(
    name: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ProviderOut:
    """Get one provider profile (404 if absent)."""
    return _provider_out(await svc.get(name))


@router.patch("/{name}", response_model=ProviderOut)
async def update_provider(
    name: str,
    body: ProviderPatch,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Partially update a provider profile."""
    resource = await svc.update(
        name,
        protocol=body.protocol,
        base_url=body.base_url,
        secret_value=body.secret_value,
        compatible_agents=body.compatible_agents,
        models=_curated(body.models),
        description=body.description,
        actor=actor,
    )
    return _provider_out(resource)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_provider(
    name: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Delete a provider profile (404 if absent)."""
    await svc.delete(name, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{name}/activate", response_model=ActivateOut)
async def activate_provider(
    name: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ActivateOut:
    """Switch: make this profile active for its wire format and project it."""
    result = await svc.activate(name, actor=actor)
    return ActivateOut(
        activated=result.activated,
        protocol=result.protocol,  # type: ignore[arg-type]
        projected=result.projected,
        skipped=result.skipped,
    )


@router.post("/use-builtin/{wire}", response_model=DeactivateOut)
async def use_builtin_provider(
    wire: Protocol,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DeactivateOut:
    """Switch this wire's agent(s) back to their OWN built-in login: remove
    Coffer's projection from the native config and clear the active connection.
    Idempotent — a no-op when the agent already runs built-in."""
    result = await svc.deactivate(wire, actor=actor)
    return DeactivateOut(
        protocol=result.protocol,  # type: ignore[arg-type]
        deprojected=result.deprojected,
        previous=result.previous,
    )


@router.post("/{name}/internal-default", response_model=ProviderOut)
async def set_internal_default_provider(
    name: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Make this connection Coffer's internal-engine default (≤1 globally).

    Clears the flag on every other connection first, so setting a new default
    moves it off the previous one. 404 if the connection is absent.
    """
    return _provider_out(await svc.set_internal_default(name, actor=actor))
