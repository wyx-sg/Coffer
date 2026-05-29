# backend/coffer/surfaces/http/retention_routes.py
"""/api/v1/retention/* — retention policy management."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from coffer.application.retention_service import RetentionService
from coffer.infrastructure.persistence.retention import UnknownPrunableTable
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_retention_service
from coffer.surfaces.http.schemas import (
    PruneResultOut,
    RetentionPolicyListOut,
    RetentionPolicyOut,
    RetentionPolicyUpdate,
)

router = APIRouter(
    prefix="/api/v1/retention",
    tags=["retention"],
    dependencies=[Depends(require_token)],
)


@router.get("/policies", response_model=RetentionPolicyListOut)
async def list_policies(
    svc: RetentionService = Depends(get_retention_service),  # noqa: B008
) -> RetentionPolicyListOut:
    views = await svc.list_policies()
    return RetentionPolicyListOut(
        policies=[
            RetentionPolicyOut(
                table_name=v.table.name,
                display_name=v.table.display_name,
                description=v.table.description,
                default_retention_days=v.table.default_retention_days,
                retention_days=v.retention_days,
                last_pruned_at=v.last_pruned_at,
                last_pruned_rows=v.last_pruned_rows,
            )
            for v in views
        ]
    )


@router.patch(
    "/policies/{table_name}",
    response_model=RetentionPolicyOut,
)
async def update_policy(
    table_name: str,
    body: RetentionPolicyUpdate,
    svc: RetentionService = Depends(get_retention_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> RetentionPolicyOut:
    await svc.set_retention(
        table_name=table_name,
        days=body.retention_days,
        actor=actor,
    )
    # Re-read so the returned view reflects the change
    for v in await svc.list_policies():
        if v.table.name == table_name:
            return RetentionPolicyOut(
                table_name=v.table.name,
                display_name=v.table.display_name,
                description=v.table.description,
                default_retention_days=v.table.default_retention_days,
                retention_days=v.retention_days,
                last_pruned_at=v.last_pruned_at,
                last_pruned_rows=v.last_pruned_rows,
            )
    # Shouldn't reach — set_retention would have raised UnknownPrunableTable
    raise UnknownPrunableTable(table_name)


@router.post("/prune", response_model=PruneResultOut)
async def prune_now(
    body: dict[str, object] | None = Body(default=None),  # noqa: B008
    svc: RetentionService = Depends(get_retention_service),  # noqa: B008
) -> PruneResultOut:
    raw = (body or {}).get("table_name") if body else None
    table_name: str | None = str(raw) if raw is not None else None
    result = await svc.prune(table_name=table_name)
    return PruneResultOut(tables=result)
