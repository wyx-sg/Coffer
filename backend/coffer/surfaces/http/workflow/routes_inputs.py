"""``/api/v1/workflow/runs/{run_id}/inputs`` — what a run reads (FR-032, FR-050).

Six routes over one list, and none of them decides anything.
``WorkflowInputsService`` owns all of it: which run may be changed, what a
second ``prd.pdf`` is called, whether unmounting deletes bytes. This module
turns a request into that call and a value object back onto the wire.

A run's inputs are the developer's **at any point in its life**, not only at
creation — creating a run is a template and a title and nothing else (FR-011),
so this is now the only way anything gets mounted. A collection nobody thought
of until the second stage is mounted then, and one that turned out to mislead is
unmounted while the run is going. Every route that changes something answers
with the inputs *after* the change, so a client never has to ask twice.

The upload has a route of its own rather than a ``kind: file`` body on the one
next to it, because it carries **bytes** rather than a reference — a different
content type is a different request, and pretending otherwise would mean a JSON
body with a base64 field in it. The file lands under the run's own directory and
its ``ref`` is the path relative to that directory, which is what a node is told
and what the agent opens from its working directory (FR-051).

A NOTE is the developer's own writing rather than a document they were given
(FR-069), so it too carries a body — and unlike an upload it can be rewritten,
because a thought is not finished when it is first written down. It keeps its
ref across a rewrite: a node that has already read the run's inputs knows the
note by that name.

None of these carries a ``version``. An input is not a move: mounting one does
not advance the run, and two developers mounting two collections have not
conflicted — they have mounted two collections. The two refusals that DO apply
are about the run rather than the command, and the service applies them both: a
run another machine owns (FR-012) and a run that has ended (FR-013).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from coffer.application.workflow.inputs_service import WorkflowInputsService
from coffer.domain.workflow.run import RunInputKind
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workflow.converters import mounted_out
from coffer.surfaces.http.workflow.dependencies import get_workflow_inputs_service
from coffer.surfaces.http.workflow.schemas import (
    InputListOut,
    RunInputIn,
    RunNoteEditIn,
    RunNoteIn,
)

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
    dependencies=[Depends(require_token)],
)


@router.get("/runs/{run_id}/inputs", response_model=InputListOut)
async def list_inputs(
    run_id: str,
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """What this run reads — collections, uploaded files and links (FR-032)."""
    return InputListOut(items=mounted_out(await inputs.list_inputs(run_id)))


@router.post(
    "/runs/{run_id}/inputs",
    response_model=InputListOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_input(
    run_id: str,
    body: RunInputIn,
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """Mount a knowledge collection or a link on a running run (FR-050).

    The request shape is narrower than the stored one: ``size``, ``path`` and
    ``mount`` are what the server made of the request, not things a caller gets
    to assert about its own upload. An uploaded FILE does not come through here
    — it has its own route, because it carries a body rather than a reference
    and its ``ref`` is the store's to choose.
    """
    items = await inputs.add_input(
        # The wire narrows the enum to the kinds that travel as a reference;
        # the service's own guard narrows it again for every other caller.
        run_id,
        kind=RunInputKind(body.kind),
        ref=body.ref,
        label=body.label,
    )
    return InputListOut(items=mounted_out(items))


@router.post(
    "/runs/{run_id}/inputs/uploads",
    response_model=InputListOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_input(
    run_id: str,
    file: UploadFile = File(...),  # noqa: B008
    label: str | None = Form(default=None),
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """Upload a file for this run to read (FR-051).

    The bytes are read here and handed over whole; where they land and what name
    survives a hostile one are questions about paths, and they are answered
    where the path guard is rather than in a route that happened to receive a
    multipart body.
    """
    items = await inputs.upload_input(
        run_id,
        filename=file.filename or "upload",
        content=await file.read(),
        label=label,
    )
    return InputListOut(items=mounted_out(items))


@router.post(
    "/runs/{run_id}/inputs/notes",
    response_model=InputListOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_note(
    run_id: str,
    body: RunNoteIn,
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """Write a note of your own into the run's inputs (FR-069).

    It becomes a markdown file under the run's own directory, listed to every
    node as the developer's own words. An image pasted into it is an ordinary
    upload the note refers to by name, which is why there is no second story
    here about where bytes go.
    """
    items = await inputs.add_note(run_id, title=body.title, text=body.text)
    return InputListOut(items=mounted_out(items))


@router.put("/runs/{run_id}/inputs/notes/{input_ref}", response_model=InputListOut)
async def rewrite_note(
    run_id: str,
    input_ref: str,
    body: RunNoteEditIn,
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """Replace a note's contents, keeping its name (FR-069)."""
    items = await inputs.rewrite_note(run_id, input_ref, text=body.text)
    return InputListOut(items=mounted_out(items))


@router.delete("/runs/{run_id}/inputs/{input_ref:path}", response_model=InputListOut)
async def remove_input(
    run_id: str,
    input_ref: str,
    inputs: WorkflowInputsService = Depends(get_workflow_inputs_service),  # noqa: B008
) -> InputListOut:
    """Unmount an input. An uploaded file's bytes go with it.

    The path parameter is a ``path`` converter rather than a plain segment
    because a link's ``ref`` is a URL: the ASGI server percent-decodes the path
    before the router ever sees it, so a dutifully encoded ``%2F`` arrives as a
    slash and a plain segment would 404 on it. ``uploads`` next door is a POST,
    so the greedy match cannot swallow it.
    """
    return InputListOut(items=mounted_out(await inputs.remove_input(run_id, input_ref)))
