"""/api/v1/resources/* — kind-agnostic Resource CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.schemas import (
    ResourceCreate,
    ResourceListOut,
    ResourceOut,
    ResourceScopeOut,
    ResourceScopeUpdate,
    ResourceUpdate,
)

router = APIRouter(
    prefix="/api/v1/resources",
    tags=["resources"],
    dependencies=[Depends(require_token)],
)


def _to_out(r: Resource) -> ResourceOut:
    return ResourceOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        description=r.description,
        config=r.config,
        scope=r.scope,
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


_actor = get_actor


@router.get("", response_model=ResourceListOut)
async def list_resources(
    kind: str | None = Query(default=None),
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceListOut:
    rs = await svc.list(kind=kind)
    return ResourceListOut(resources=[_to_out(r) for r in rs])


@router.post(
    "",
    response_model=ResourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_resource(
    body: ResourceCreate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.register(
        kind=body.kind,
        name=body.name,
        config=body.config,
        description=body.description,
        actor=actor,
    )
    return _to_out(r)


@router.get("/{kind}/{name}", response_model=ResourceOut)
async def get_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceOut:
    r = await svc.get(ResourceRef(kind, name))
    return _to_out(r)


@router.patch("/{kind}/{name}", response_model=ResourceOut)
async def update_resource(
    kind: str,
    name: str,
    body: ResourceUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    if body.config is None:
        existing = await svc.get(ResourceRef(kind, name))
        config = existing.config
    else:
        config = body.config
    r = await svc.update_config(
        ResourceRef(kind, name),
        new_config=config,
        actor=actor,
        description=body.description,
    )
    return _to_out(r)


@router.delete("/{kind}/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete(ResourceRef(kind, name), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kind}/{name}/enable", response_model=ResourceOut)
async def enable_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.set_enabled(ResourceRef(kind, name), enabled=True, actor=actor)
    return _to_out(r)


@router.post("/{kind}/{name}/disable", response_model=ResourceOut)
async def disable_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.set_enabled(ResourceRef(kind, name), enabled=False, actor=actor)
    return _to_out(r)


@router.get("/{kind}/{name}/scope", response_model=ResourceScopeOut)
async def get_resource_scope(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceScopeOut:
    r = await svc.get(ResourceRef(kind, name))
    axes = svc.scope_axes(r.kind)
    return ResourceScopeOut(scope=r.scope, axes=list(axes))


@router.put("/{kind}/{name}/scope", response_model=ResourceOut)
async def update_resource_scope(
    kind: str,
    name: str,
    body: ResourceScopeUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    # Deliberately NOT gated on allow_lifecycle_kind — scope is a
    # framework-level concern orthogonal to a kind's creation invariants
    # (ResourceService.update_scope, ADR-045).
    r = await svc.update_scope(ResourceRef(kind, name), body.scope, actor=actor)
    return _to_out(r)
