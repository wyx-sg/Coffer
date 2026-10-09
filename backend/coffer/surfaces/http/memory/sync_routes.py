"""``/api/v1/memory/sync/*``: the memory sync (spec memory "Manage memory
sync in the web UI").

The sync's state, **Sync now**, the pending preview's **Write** and
**Cancel**, **Undo sync…**, the person's answer to "Codex imports Claude
Code's memories itself", the hub's memories for one project with where each
was written here, and **Curate now**.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from coffer.application.memory.sync_report import SyncReport
from coffer.application.memory.sync_service import MemorySyncService
from coffer.application.memory.sync_view import MemorySyncView, SyncState
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.sync_dependencies import get_sync_service, get_sync_view

router = APIRouter(
    prefix="/api/v1/memory/sync",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


class WriterStatusOut(BaseModel):
    state: str
    path: str = ""
    reason: str = ""


class CurationStateOut(BaseModel):
    #: ``on`` / ``off`` / ``unknown``: the agent's own memory.
    memory: str
    #: ``on`` / ``off`` / ``unknown``: the agent's own curation.
    curation: str


class SyncAgentOut(BaseModel):
    agent: str
    agent_type: str
    writer: WriterStatusOut
    curation: CurationStateOut
    #: How many copies this machine holds in the agent, by state.
    copies: dict[str, int] = Field(default_factory=dict)


class SyncProjectOut(BaseModel):
    key: str
    folder: str
    memories: int
    #: How many of the project's memories each agent type published.
    agents: dict[str, int] = Field(default_factory=dict)
    #: The project's checkout on this machine, or ``null`` (held back).
    checked_out: str | None = None


class MemorySyncStateOut(BaseModel):
    running: bool
    last_synced_at: str = ""
    last_report: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] | None = None
    codex_imports_claude: bool | None = None
    agents: list[SyncAgentOut] = Field(default_factory=list)
    projects: list[SyncProjectOut] = Field(default_factory=list)
    global_memories: int = 0
    machine: str = ""


class MemorySyncReportOut(BaseModel):
    """What one sync, write or undo did (the ``memory_synced`` details)."""

    details: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)


class HubEntryOut(BaseModel):
    id: str
    title: str
    description: str
    type: str
    project: str = ""
    origin_machine: str
    origin_agent: str
    created_at: str
    updated_at: str
    #: ``agent type → copy state`` on this machine (``written``, ``edited``,
    #: ``removed``, ``held_back``, ``deferred``, ``rules``, ``origin``,
    #: ``pending``).
    copies: dict[str, str] = Field(default_factory=dict)


class HubEntryListOut(BaseModel):
    project: str
    entries: list[HubEntryOut] = Field(default_factory=list)


class CodexImportIn(BaseModel):
    #: ``true`` when Codex imports Claude Code's memories itself, ``null`` to forget.
    value: bool | None = None


class CurateIn(BaseModel):
    agent_type: str


class CurateOut(BaseModel):
    started: bool


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
                curation=CurationStateOut(memory=a.curation.memory, curation=a.curation.curation),
                copies=a.copies,
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
        global_memories=state.global_memories,
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
    project: str = Query("", description="A project key; empty for global memories."),
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


@router.post("/curate", response_model=CurateOut)
async def curate_now(
    body: CurateIn,
    view: MemorySyncView = Depends(get_sync_view),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CurateOut:
    """**Curate now**: start the agent headless with a prompt to consolidate
    its own memory."""
    return CurateOut(started=await view.curate(body.agent_type, actor))


__all__ = ["router"]
