"""``/api/v1/memory``: the Memory page's reads, a person's edit or delete of a
memory file, the tidy's start and finish, and the text a session is handed
(spec memory "Show and edit memory on the Memory page", "Tidy memory as one
change", "Hand a session its project's memories at start")."""

from __future__ import annotations

import asyncio
import pathlib

from fastapi import APIRouter, Depends, Query, Response

from coffer.application.memory.context import session_context
from coffer.application.memory.service import MemoryService
from coffer.application.memory.tidy import MemoryTidy, tidy_prompt
from coffer.domain.memory.hub import Topic
from coffer.infrastructure.memory.hub_store import TopicFile
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.memory.dependencies import get_memory_service, get_memory_tidy
from coffer.surfaces.http.memory.schemas import (
    MemoryContextOut,
    MemoryFileIn,
    MemoryFileOut,
    MemoryProjectOut,
    MemoryStateOut,
    MemoryTidyFinishIn,
    MemoryTidyFinishOut,
    MemoryTidyStatusOut,
    MemoryTopicListOut,
    MemoryTopicOut,
    TidyHandoffOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def _topic(t: Topic) -> MemoryTopicOut:
    return MemoryTopicOut(
        project=t.project,
        name=t.name,
        title=t.title,
        type=t.type,
        updated=t.updated,
        body=t.body,
        problems=list(t.problems),
    )


def _file(svc: MemoryService, f: TopicFile) -> MemoryFileOut:
    t = f.topic
    return MemoryFileOut(
        **_topic(t).model_dump(),
        path=str(svc.hub.projects_root() / t.project / t.name),
        text=f.text,
        digest=f.digest,
    )


@router.get("", response_model=MemoryStateOut)
async def memory_state(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    tidy: MemoryTidy = Depends(get_memory_tidy),  # noqa: B008
) -> MemoryStateOut:
    """The projects that hold memories, whether a tidy is open, and the
    prompt **Tidy** hands to the agent."""
    await tidy.expire()
    projects = await svc.projects()
    status = tidy.status()
    return MemoryStateOut(
        folder_path=svc.folder_path(),
        projects=[
            MemoryProjectOut(
                folder=p.folder, topics=p.topics, problems=p.problems, updated=p.updated
            )
            for p in projects
        ],
        tidy_running=status.running,
        tidy_started_at=status.started_at,
        tidy_handoff=TidyHandoffOut(prompt=tidy_prompt(svc.folder_path(), projects)),
    )


@router.get("/projects/{project}", response_model=MemoryTopicListOut)
async def list_topics(
    project: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryTopicListOut:
    return MemoryTopicListOut(
        project=project, topics=[_topic(t) for t in await svc.topics(project)]
    )


@router.get("/projects/{project}/{name}", response_model=MemoryFileOut)
async def get_file(
    project: str,
    name: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryFileOut:
    return _file(svc, await svc.read(project, name))


@router.put("/projects/{project}/{name}", response_model=MemoryFileOut)
async def put_file(
    project: str,
    name: str,
    body: MemoryFileIn,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> MemoryFileOut:
    """Replace a memory file's text; refused ``MEMORY_FILE_STALE`` when it
    changed since ``expected`` was read."""
    await svc.write(project, name, body.text, expected=body.expected, actor=actor)
    return _file(svc, await svc.read(project, name))


@router.delete("/projects/{project}/{name}", status_code=204, response_class=Response)
async def delete_file(
    project: str,
    name: str,
    expected: str = Query(..., description="The digest the page read."),
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    await svc.delete(project, name, expected=expected, actor=actor)
    return Response(status_code=204)


@router.post("/tidy/start", response_model=MemoryTidyStatusOut)
async def start_tidy(
    tidy: MemoryTidy = Depends(get_memory_tidy),  # noqa: B008
) -> MemoryTidyStatusOut:
    """Open a tidy: until it finishes, the edits under memory/ are kept for
    one commit."""
    s = await tidy.start()
    return MemoryTidyStatusOut(running=s.running, started_at=s.started_at)


@router.post("/tidy/finish", response_model=MemoryTidyFinishOut)
async def finish_tidy(
    body: MemoryTidyFinishIn,
    tidy: MemoryTidy = Depends(get_memory_tidy),  # noqa: B008
    actor: str = Depends(get_actor),
) -> MemoryTidyFinishOut:
    """Close the tidy and commit what it changed as one commit carrying the report."""
    return MemoryTidyFinishOut(version=await tidy.finish(body.summary, actor=actor))


@router.get("/context", response_model=MemoryContextOut)
async def get_context(
    cwd: str = Query(..., description="A session's working directory."),
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryContextOut:
    """What a session started in ``cwd`` is handed."""
    vault = svc.hub.root().parent
    text = await asyncio.to_thread(session_context, pathlib.Path(cwd), vault=vault)
    return MemoryContextOut(text=text)


__all__ = ["router"]
