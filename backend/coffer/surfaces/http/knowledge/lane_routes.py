"""The non-entry lanes of a knowledge scope: handoff / rules / consolidation-log.

Registered on the shared ``knowledge`` router (imported from ``routes``) to keep
each module under the file-size budget. The GET reads mirror ``get_rules``:
auto-provision for the global name, ``Depends(require_token)`` (router-level),
read-only, 200 with empty content for an empty scope (never 404). The DELETEs
mirror ``delete_entry``: actor from ``X-Coffer-Actor``, 204 on success, 404 when
the lane file does not exist.
"""

from __future__ import annotations

from fastapi import Depends, Response, status

from coffer.application.knowledge import lane_reads
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import Actor
from coffer.surfaces.http.dependencies import get_knowledge_service
from coffer.surfaces.http.knowledge.routes import _actor, _ensure_auto, router
from coffer.surfaces.http.knowledge.schemas import (
    ConsolidationLogOut,
    HandoffOut,
    HandoffSceneOut,
)


@router.get("/{name}/handoff", response_model=HandoffOut)
async def get_handoff(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> HandoffOut:
    """List the scope's per-branch ``handoff/<slug>.md`` scenes."""
    await _ensure_auto(k_svc, name)
    scenes = await lane_reads.handoff_for_store(name, k_svc.resolved_scope)
    return HandoffOut(
        scenes=[
            HandoffSceneOut(
                branch=s.branch,
                text=s.text,
                updated_at=s.updated_at,
                path=s.path,
                folder_path=s.folder_path,
            )
            for s in scenes
        ]
    )


@router.get("/{name}/consolidation-log", response_model=ConsolidationLogOut)
async def get_consolidation_log(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> ConsolidationLogOut:
    """Read the scope-root ``consolidation-log.md`` (``text=None`` when absent)."""
    await _ensure_auto(k_svc, name)
    log = await lane_reads.consolidation_log_for_store(name, k_svc.resolved_scope)
    return ConsolidationLogOut(text=log.text, path=log.path, folder_path=log.folder_path)


# --- lane deletes -----------------------------------------------------------


@router.delete(
    "/{name}/handoff/{branch}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_handoff_branch(
    name: str,
    branch: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Delete one ``handoff/<branch-slug>.md`` scene (lane is not indexed)."""
    await k_svc.delete_lane(scope_name=name, lane="handoff", identifier=branch, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}/rules",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_rules(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Remove the whole ``rules/`` lane (lane is not indexed)."""
    await k_svc.delete_lane(scope_name=name, lane="rules", identifier="", actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}/consolidation-log",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_consolidation_log(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Delete the scope-root ``consolidation-log.md`` (no changelog self-append)."""
    await k_svc.delete_lane(scope_name=name, lane="consolidation-log", identifier="", actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
