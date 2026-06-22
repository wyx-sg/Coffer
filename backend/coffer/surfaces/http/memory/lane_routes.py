"""Slice-7 four-lane routes: journal / handoff / rules / consolidation-log.

Registered on the shared ``memory`` router (imported from ``routes``) to keep
each module under the file-size budget. The GET reads mirror ``get_rules``:
``ensure_store`` for the global name, ``Depends(require_token)`` (router-level),
read-only, 200 with empty content for an empty store (never 404). The DELETEs
mirror ``forget_fact``: actor from ``X-Coffer-Actor``, 204 on success, 404 when
the lane file does not exist.
"""

from __future__ import annotations

from fastapi import Depends, Response, status

from coffer.application.memory import lane_reads
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service import MemoryService
from coffer.domain.memory.fact import Actor
from coffer.surfaces.http.dependencies import get_memory_service
from coffer.surfaces.http.memory.routes import _actor, router
from coffer.surfaces.http.memory.schemas import (
    ConsolidationLogOut,
    HandoffOut,
    HandoffSceneOut,
    JournalFileOut,
    JournalOut,
)


@router.get("/{name}/journal", response_model=JournalOut)
async def get_journal(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> JournalOut:
    """List the store's ``journal/<period>.md`` files, newest period first."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    files = await lane_reads.journal_for_store(name, mem_svc.resolved_store)
    return JournalOut(
        files=[
            JournalFileOut(period=f.period, text=f.text, path=f.path, folder_path=f.folder_path)
            for f in files
        ]
    )


@router.get("/{name}/handoff", response_model=HandoffOut)
async def get_handoff(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> HandoffOut:
    """List the store's per-branch ``handoff/<slug>.md`` scenes."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    scenes = await lane_reads.handoff_for_store(name, mem_svc.resolved_store)
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
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> ConsolidationLogOut:
    """Read the store-root ``consolidation-log.md`` (``text=None`` when absent)."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    log = await lane_reads.consolidation_log_for_store(name, mem_svc.resolved_store)
    return ConsolidationLogOut(text=log.text, path=log.path, folder_path=log.folder_path)


# --- lane deletes -----------------------------------------------------------


@router.delete(
    "/{name}/journal/{period}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_journal_period(
    name: str,
    period: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Delete one ``journal/<period>.md`` file + its recall-index rows."""
    await mem_svc.delete_lane(store_name=name, lane="journal", identifier=period, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}/handoff/{branch}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_handoff_branch(
    name: str,
    branch: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Delete one ``handoff/<branch-slug>.md`` scene (lane is not indexed)."""
    await mem_svc.delete_lane(store_name=name, lane="handoff", identifier=branch, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}/rules",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_rules(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Remove the whole ``rules/`` lane (lane is not indexed)."""
    await mem_svc.delete_lane(store_name=name, lane="rules", identifier="", actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{name}/consolidation-log",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_consolidation_log(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    """Delete the store-root ``consolidation-log.md`` (no changelog self-append)."""
    await mem_svc.delete_lane(store_name=name, lane="consolidation-log", identifier="", actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
