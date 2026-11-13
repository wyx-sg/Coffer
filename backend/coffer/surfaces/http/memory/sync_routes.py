"""``/api/v1/memory/sync/*``: the memory sync (spec memory "Manage memory
sync in the web UI and on the command line").

The sync's state, **Sync now**, the pending preview's **Write** and
**Cancel**, **Undo sync…**, the person's answer to "Codex imports Claude
Code's memories itself", the hub's memories for one project with where each
was written here, and one memory's text with the file each agent holds it in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from coffer.application.memory.sync_report import SyncReport
from coffer.application.memory.sync_service import MemorySyncService
from coffer.application.memory.sync_view import MemorySyncView, SyncState
from coffer.domain.errors import ResourceNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.sync_dependencies import get_sync_service, get_sync_view
from coffer.surfaces.http.memory.sync_schemas import (
    CodexImportIn,
    EntryCopyOut,
    HubEntryDetailOut,
    HubEntryListOut,
    HubEntryOut,
    MemorySyncReportOut,
    MemorySyncStateOut,
    SyncAgentOut,
    SyncLocationOut,
    SyncProjectOut,
    WriterStatusOut,
)

router = APIRouter(
    prefix="/api/v1/memory/sync",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def _report(report: SyncReport) -> MemorySyncReportOut:
    return MemorySyncReportOut(details=report.details(), summary=report.summary())


def _state(state: SyncState) -> MemorySyncStateOut:
    return MemorySyncStateOut(
        running=state.running,
        last_synced_at=state.last_synced_at,
        last_report=state.last_report,
        preview=state.preview,
        codex_imports_claude=state.codex_imports_claude,
        agents=[
            SyncAgentOut(
                agent=a.agent,
                agent_type=a.agent_type,
                writer=WriterStatusOut(**a.writer),
                copies=a.copies,
                locations=[
                    SyncLocationOut(
                        name=loc.name,
                        path=loc.path,
                        writer=WriterStatusOut(**loc.writer),
                        copies=loc.copies,
                    )
                    for loc in a.locations
                ],
            )
            for a in state.agents
        ],
        projects=[
            SyncProjectOut(
                key=p.key,
                folder=p.folder,
                memories=p.memories,
                agents=p.agents,
                checked_out=p.checked_out,
            )
            for p in state.projects
        ],
        machine=state.machine,
    )


@router.get("/state", response_model=MemorySyncStateOut)
async def sync_state(
    view: MemorySyncView = Depends(get_sync_view),  # noqa: B008
) -> MemorySyncStateOut:
    return _state(await view.state())


@router.post("/run", response_model=MemorySyncReportOut)
async def sync_now(
    svc: MemorySyncService = Depends(get_sync_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> MemorySyncReportOut:
    """**Sync now**: 409 ``MEMORY_SYNC_RUNNING`` while a sync runs."""
    return _report(await svc.sync(actor))


@router.post("/preview/write", response_model=MemorySyncReportOut)
async def write_preview(
    svc: MemorySyncService = Depends(get_sync_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> MemorySyncReportOut:
    return _report(await svc.write_preview(actor))


@router.post("/preview/cancel", status_code=204, response_class=Response)
async def cancel_preview(
    svc: MemorySyncService = Depends(get_sync_service),  # noqa: B008
) -> Response:
    await svc.cancel_preview()
    return Response(status_code=204)


@router.post("/undo", response_model=MemorySyncReportOut)
async def undo_sync(
    svc: MemorySyncService = Depends(get_sync_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> MemorySyncReportOut:
    """**Undo sync…**: removes Coffer's copies from this machine's agents and
    turns automatic sync off."""
    return _report(await svc.undo(actor))


@router.put("/codex-import", status_code=204, response_class=Response)
async def set_codex_import(
    body: CodexImportIn,
    svc: MemorySyncService = Depends(get_sync_service),  # noqa: B008
) -> Response:
    await svc.set_codex_imports_claude(body.value)
    return Response(status_code=204)


@router.get("/entries", response_model=HubEntryListOut)
async def list_entries(
    project: str = Query(..., description="A project key."),
    view: MemorySyncView = Depends(get_sync_view),  # noqa: B008
) -> HubEntryListOut:
    rows = await view.entries(project)
    return HubEntryListOut(
        project=project,
        entries=[
            HubEntryOut(
                id=r.entry.id,
                title=r.entry.title,
                description=r.entry.description,
                type=r.entry.type,
                project=r.entry.project,
                origin_machine=r.entry.origin.machine,
                origin_agent=r.entry.origin.agent,
                created_at=r.entry.created_at,
                updated_at=r.entry.updated_at,
                copies=r.copies,
            )
            for r in rows
        ],
    )


@router.get("/entries/{entry_id}", response_model=HubEntryDetailOut)
async def get_entry(
    entry_id: str,
    view: MemorySyncView = Depends(get_sync_view),  # noqa: B008
) -> HubEntryDetailOut:
    """One memory's text and where each agent on this machine holds it."""
    detail = await view.entry(entry_id)
    if detail is None:
        raise ResourceNotFound(f"memory {entry_id}")
    e = detail.entry
    return HubEntryDetailOut(
        id=e.id,
        title=e.title,
        description=e.description,
        type=e.type,
        project=e.project,
        origin_machine=e.origin.machine,
        origin_agent=e.origin.agent,
        created_at=e.created_at,
        updated_at=e.updated_at,
        body=detail.body,
        copies=[
            EntryCopyOut(agent_type=c.agent_type, state=c.state, path=c.path) for c in detail.copies
        ],
    )


__all__ = ["router"]
