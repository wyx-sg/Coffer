"""``…/artifacts`` and ``…/promotion`` — what a run produced, and where it goes.

The listing regenerates the catalogue rather than reading whatever ``CATALOG.md``
happens to hold: the catalogue is generated from the directory and never
hand-maintained (spec workflow "Generate the index of earlier tasks"), so
re-rendering it is how this route stays true, and re-rendering the same directory
twice produces the same bytes.

Promotion copies; it never moves ("Promote what a run is made of into a
knowledge collection"). The run's own directory is left exactly as it was, which
is what makes a delivery's output safe to feed to the next delivery as an input.
It is deliberately **not** guarded against a finished run — a finished run is
precisely the one worth promoting.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from coffer.application.workflow.catalogue import regenerate_catalogue
from coffer.application.workflow.context_composer import parse_inputs
from coffer.application.workflow.ports import ArtifactStorePort, KnowledgeInputPort
from coffer.application.workflow.promotion import references_markdown
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workflow.converters import (
    artifact_out,
)
from coffer.surfaces.http.workflow.dependencies import (
    get_workflow_artifact_store,
    get_workflow_knowledge_input,
    get_workflow_run_service,
)
from coffer.surfaces.http.workflow.schemas import (
    ArtifactListOut,
    PromotionIn,
    PromotionOut,
    RunFileOut,
)

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    dependencies=[Depends(require_token)],
)


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListOut)
async def list_artifacts(
    run_id: str,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    artifacts: ArtifactStorePort = Depends(get_workflow_artifact_store),  # noqa: B008
) -> ArtifactListOut:
    """Every artifact the run has produced, attributed to node and attempt."""
    await runs.get_run(run_id)  # 404 for a run that is not there
    catalogue = regenerate_catalogue(artifacts, run_id)
    return ArtifactListOut(
        catalogue=catalogue,
        items=[artifact_out(entry) for entry in artifacts.list_artifacts(run_id)],
    )


@router.get("/runs/{run_id}/files", response_model=RunFileOut)
async def read_run_file(
    run_id: str,
    path: str = Query(min_length=1, description="Path relative to the run's own directory."),
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    artifacts: ArtifactStorePort = Depends(get_workflow_artifact_store),  # noqa: B008
) -> RunFileOut:
    """One file the run reads or wrote, so the UI can show it (spec
    workflow "Read a run's files from the app, bounded").

    Read-only, and bounded: the path is guarded segment by segment against the
    run's own directory, a file that is not there is a 404 rather than an empty
    preview, and the store caps how much of a long file comes back.
    """
    await runs.get_run(run_id)  # 404 for a run that is not there
    found = artifacts.read_file(run_id, path)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    return RunFileOut(
        path=found.path,
        name=found.name,
        size=found.size,
        text=found.text,
        truncated=found.truncated,
    )


@router.get(
    "/runs/{run_id}/files/raw",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def read_run_file_bytes(
    run_id: str,
    path: str = Query(min_length=1, description="Path relative to the run's own directory."),
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    artifacts: ArtifactStorePort = Depends(get_workflow_artifact_store),  # noqa: B008
) -> Response:
    """One file's BYTES, so an image the run holds can be displayed (spec
    workflow "Keep the developer's own notes in a run's context").

    The sibling above answers "show this to a person" and returns text; this
    answers "put this in an <img>". Same guard and the same cap — what differs
    is that a screenshot pasted into a note has no text to preview and is still
    the thing the note is about.

    The media type is the store's answer, narrowed to a list it is willing to
    hand a browser. Everything else is served opaque, because a run's directory
    holds whatever its agent wrote.
    """
    await runs.get_run(run_id)  # 404 for a run that is not there
    found = artifacts.read_bytes(run_id, path)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    content, media_type = found
    return Response(
        content=content,
        media_type=media_type,
        # Nothing here is a document this app wants a browser to navigate to.
        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/runs/{run_id}/promotion",
    response_model=PromotionOut,
    status_code=status.HTTP_201_CREATED,
)
async def promote_artifacts(
    run_id: str,
    body: PromotionIn,
    runs: WorkflowRunService = Depends(get_workflow_run_service),  # noqa: B008
    artifacts: ArtifactStorePort = Depends(get_workflow_artifact_store),  # noqa: B008
    knowledge: KnowledgeInputPort = Depends(get_workflow_knowledge_input),  # noqa: B008
) -> PromotionOut:
    """Copy what a run is made of into a knowledge collection (spec
    workflow "Promote what a run is made of into a knowledge
    collection").

    Its artifacts, its uploaded files and its notes travel as files; the links,
    collections and repositories it read travel as one ``references.md``,
    because those are not the run's bytes to copy and "this delivery read that"
    is the part worth keeping anyway.

    The collection is created if it is not there and added to if it is — which
    is the port's contract, not a branch taken here: the knowledge kind is
    behind a seam this package may not reach around.
    """
    run = await runs.get_run(run_id)  # 404 for a run that is not there
    destination = await knowledge.create_collection(body.collection)
    copied = artifacts.collect_run_files(
        run_id,
        destination,
        references=references_markdown(run.title, parse_inputs(run.inputs)),
    )
    return PromotionOut(collection=body.collection, copied=copied)
