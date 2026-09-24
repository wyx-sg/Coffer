"""/api/v1/resources/* — kind-agnostic Resource CRUD.

A resource whose kind belongs to a switched-off experimental feature is out of
reach here as well as on its own routes (spec experimental-features "Close
every surface of a switched-off feature"): a route that names it — by
``kind``, or by a uid whose row is of that kind — answers 404
``FEATURE_DISABLED``, and a list leaves its rows out. Nothing is deleted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.feature_dependencies import kind_enabled, require_kind_enabled
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
        uid=r.uid,
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


async def _reachable(svc: ResourceService, uid: str) -> Resource:
    """The row ``uid`` names, refused while its kind's feature is off."""
    r = await svc.get(uid)
    require_kind_enabled(r.kind)
    return r


@router.get("", response_model=ResourceListOut)
async def list_resources(
    kind: str | None = Query(default=None),
    name: str | None = Query(
        default=None,
        description=(
            "Filter by exact label. This is the ONE place a name may be used to "
            "find a resource: it is how a surface that started from what a human "
            "typed — the CLI — turns that into the uid every other route takes."
        ),
    ),
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceListOut:
    if kind is not None:
        require_kind_enabled(kind)
    rs = [r for r in await svc.list(kind=kind) if kind_enabled(r.kind)]
    if name is not None:
        rs = [r for r in rs if r.name == name]
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
    require_kind_enabled(body.kind)
    r = await svc.register(
        kind=body.kind,
        name=body.name,
        config=body.config,
        description=body.description,
        actor=actor,
    )
    return _to_out(r)


@router.get("/{uid}", response_model=ResourceOut)
async def get_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceOut:
    return _to_out(await _reachable(svc, uid))


@router.patch("/{uid}", response_model=ResourceOut)
async def update_resource(
    uid: str,
    body: ResourceUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    """Edit a resource's label, description or config.

    ``name`` is an ordinary field here, at the same level as ``description``,
    which is the whole user-facing point of the identity change: while the name
    WAS the identity, moving it needed its own route, and only one kind ever
    got one.

    An ABSENT field leaves what is stored alone, and so does an explicit null.
    ``model_fields_set``, not a value comparison: every field here is optional
    and ``None`` is a legal VALUE for ``description``, so "the client did not
    mention it" and "the client asked to clear it" are the same ``None`` and can
    only be told apart by which keys the body carried. Comparing values instead
    read a rename-only PATCH as a request to clear the description, and wiped it
    — silently, with a spurious update event in the audit trail to match. For
    ``config`` there is no clearing at all: a resource without a config is not a
    state any kind has, so a client that wanted it emptied would say ``{}``, and
    one that said null is a client that filled in a field it had no value for.
    """
    sent = body.model_fields_set
    edits_config = "config" in sent and body.config is not None
    edits_description = "description" in sent

    # A rename ALONE touches no config, so it runs no config write. Rewriting
    # the stored config back over itself is not a no-op: it re-validates, it
    # re-probes every credential the config cites, it fires the kind's update
    # hook and it records a `resource_updated` with identical before and after.
    # A rename refused because a credential this resource mentions has since
    # been deleted is a refusal about something the caller did not touch.
    r = await _reachable(svc, uid)
    if edits_config or edits_description:
        r = await svc.update_config(
            uid,
            new_config=body.config if body.config is not None else r.config,
            actor=actor,
            description=body.description if edits_description else r.description,
        )
    # The rename comes LAST, so a refused config leaves the name alone: one
    # PATCH that renamed a resource and then rejected its config would have
    # moved the thing the caller was about to retry against.
    if body.name is not None:
        r = await svc.rename(uid, body.name, actor=actor)
    return _to_out(r)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await _reachable(svc, uid)
    await svc.delete(uid, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{uid}/enable", response_model=ResourceOut)
async def enable_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    await _reachable(svc, uid)
    return _to_out(await svc.set_enabled(uid, enabled=True, actor=actor))


@router.post("/{uid}/disable", response_model=ResourceOut)
async def disable_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    await _reachable(svc, uid)
    return _to_out(await svc.set_enabled(uid, enabled=False, actor=actor))


@router.get("/{uid}/scope", response_model=ResourceScopeOut)
async def get_resource_scope(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceScopeOut:
    r = await _reachable(svc, uid)
    return ResourceScopeOut(scope=ScopeOut.of(r.scope), supports_scope=svc.supports_scope(r.kind))


@router.put("/{uid}/scope", response_model=ResourceOut)
async def update_resource_scope(
    uid: str,
    body: ResourceScopeUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    # Deliberately NOT gated on allow_lifecycle_kind — scope is a
    # framework-level concern orthogonal to a kind's creation invariants
    # (ResourceService.update_scope, ADR: per-agent-resource-scope).
    await _reachable(svc, uid)
    scope = body.scope.to_domain() if body.scope is not None else None
    return _to_out(await svc.update_scope(uid, scope, actor=actor))
