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
    ScopeOut,
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
        scope=ScopeOut.of(r.scope),
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
    # An ABSENT field leaves what is stored alone; the service takes a whole
    # resource and would otherwise write a null over it. That mattered the
    # moment a PATCH could carry only a name: renaming a workflow was quietly
    # erasing its description, because the body said nothing about one.
    sent = body.model_fields_set
    if "config" not in sent and "description" not in sent:
        existing = await svc.get(ResourceRef(kind, name))
        config, description = existing.config, existing.description
    elif "config" not in sent:
        existing = await svc.get(ResourceRef(kind, name))
        config, description = existing.config, body.description
    elif "description" not in sent:
        existing = await svc.get(ResourceRef(kind, name))
        config, description = body.config or {}, existing.description
    else:
        config, description = body.config or {}, body.description
    r = await svc.update_config(
        ResourceRef(kind, name),
        new_config=config,
        actor=actor,
        description=description,
    )
    # The rename comes LAST, so a refused config leaves the name alone: one
    # PATCH that renamed a resource and then rejected its config would have
    # moved the thing the caller was about to retry against.
    if body.name is not None:
        r = await svc.rename(ResourceRef(kind, name), body.name, actor=actor)
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
    return ResourceScopeOut(scope=ScopeOut.of(r.scope), supports_scope=svc.supports_scope(r.kind))


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
    # (ResourceService.update_scope, ADR: per-agent-resource-scope).
    scope = body.scope.to_domain() if body.scope is not None else None
    r = await svc.update_scope(ResourceRef(kind, name), scope, actor=actor)
    return _to_out(r)
