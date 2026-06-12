"""/api/v1/memory_stores/{name}/projections/* — memory projection routes.

These live OUTSIDE the memory kind subpackage because they bridge memory and
agent (the per-kind import contracts forbid the memory kind from importing the
agent kind). The composition root wires a :class:`ProjectionService` singleton
here. The path prefix still nests under ``memory_stores`` to match the 007
OpenAPI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.memory.schemas import (
    ProjectionListOut,
    ProjectionOut,
)
from coffer.surfaces.http.projection_service import ProjectionService

router = APIRouter(
    prefix="/api/v1/memory_stores",
    tags=["projection"],
    dependencies=[Depends(require_token)],
)

# A second router under /api/v1/agents for the native-memory TAKEOVER. It lives
# here (composition root) rather than in agent_routes because it bridges agent +
# memory, which agent_routes may not import (cross-kind Contract 5b).
agent_native_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["projection"],
    dependencies=[Depends(require_token)],
)


class NativeMemoryImportItemOut(BaseModel):
    slug: str
    fact_count: int
    status: str
    project_root: str | None = None
    store_name: str | None = None
    backup_dir: str | None = None
    detail: str | None = None


class NativeMemoryImportOut(BaseModel):
    items: list[NativeMemoryImportItemOut]
    imported: int
    skipped: int


# The projection service is composition-root state; held module-local so the
# memory routes module stays free of the agent import (Contract 5e).
_projection_service: ProjectionService | None = None


def set_projection_service(svc: ProjectionService) -> None:
    global _projection_service
    _projection_service = svc


def get_projection_service() -> ProjectionService:
    if _projection_service is None:
        raise RuntimeError("projection service not initialised")
    return _projection_service


class ProjectionEstablishRequest(BaseModel):
    """The 007 ``ProjectionRequest`` plus an optional ``project_root`` so a
    SYMLINK projection of a project store can locate the agent's native dir."""

    agent_ref: str
    project_root: str | None = None


def _to_out(binding: Any) -> ProjectionOut:
    return ProjectionOut(
        agent_ref=binding.agent_ref,
        projection_mode=binding.projection_mode,
        target_path=binding.target_path,
        native_memory_disabled=binding.native_memory_disabled,
    )


@router.get("/{name}/projections", response_model=ProjectionListOut)
async def list_projections(
    name: str,
    svc: ProjectionService = Depends(get_projection_service),  # noqa: B008
) -> ProjectionListOut:
    bindings = await svc.list_projections(store_name=name)
    return ProjectionListOut(projections=[_to_out(b) for b in bindings])


@router.post("/{name}/projections", response_model=ProjectionOut)
async def establish_projection(
    name: str,
    body: ProjectionEstablishRequest,
    svc: ProjectionService = Depends(get_projection_service),  # noqa: B008
) -> ProjectionOut:
    project_root = body.project_root
    if project_root is not None:
        # Projection writes/symlinks under this path; never accept a target
        # that does not already exist as a directory (a typo'd root must not
        # be mkdir'd, and arbitrary file paths must not be rewritten). Resolve
        # symlinks FIRST and use the resolved path downstream (no
        # check-then-use gap on a swapped link).
        from pathlib import Path

        from fastapi import HTTPException

        root = Path(project_root).resolve()
        if not root.is_absolute() or not root.is_dir():
            raise HTTPException(
                status_code=400,
                detail="project_root must be an absolute path to an existing directory",
            )
        project_root = str(root)
    result = await svc.establish(
        store_name=name, agent_ref=body.agent_ref, project_root=project_root
    )
    return ProjectionOut(
        agent_ref=result.agent_ref,
        projection_mode=result.projection_mode.value,
        target_path=result.target_path,
        native_memory_disabled=result.native_memory_disabled,
        merged_existing=result.merged_existing,
    )


@router.delete(
    "/{name}/projections/{agent_ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_projection(
    name: str,
    agent_ref: str,
    svc: ProjectionService = Depends(get_projection_service),  # noqa: B008
) -> Response:
    removed = await svc.remove(store_name=name, agent_ref=agent_ref)
    if not removed:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="projection not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@agent_native_router.post("/{name}/native-memory/import", response_model=NativeMemoryImportOut)
async def import_native_memory(
    name: str,
    svc: ProjectionService = Depends(get_projection_service),  # noqa: B008
) -> NativeMemoryImportOut:
    """Take over the agent's unmanaged native memory (Claude Code only).

    Each takeover backs the original dir up to ``memory.bak-<timestamp>`` before
    symlinking, so the user's facts are never at risk. Non-Claude agents and
    undecodable slugs are no-ops/reported, never guessed."""
    suffix = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    result = await svc.take_over_claude_native_memory(agent_ref=name, backup_suffix=suffix)
    return NativeMemoryImportOut(
        items=[NativeMemoryImportItemOut(**vars(i)) for i in result.items],
        imported=result.imported,
        skipped=result.skipped,
    )
