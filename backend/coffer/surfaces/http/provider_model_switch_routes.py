"""/api/v1/providers/model-switch — review, then apply, one agent's model change
(spec provider-switching).

The preview computes the files the switch would change and writes nothing; the
apply writes them, refusing (409 ``CONFIG_FILE_STALE``) when a file the preview
showed was edited on disk since. Domain errors propagate to the app-wide handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.agent.service import AgentService
from coffer.application.provider import model_switch
from coffer.application.provider.line_diff import line_diff
from coffer.application.provider.projector import PlannedFile
from coffer.application.provider.service import ProviderService
from coffer.surfaces.http.agent_dependencies import get_agent_service
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.provider_dependencies import get_provider_service
from coffer.surfaces.http.provider_schemas import (
    ModelSwitchFile,
    ModelSwitchIn,
    ModelSwitchLine,
    ModelSwitchOut,
)

router = APIRouter(
    prefix="/api/v1/providers/model-switch",
    tags=["providers"],
    dependencies=[Depends(require_token)],
)


def _switch(body: ModelSwitchIn) -> model_switch.ModelSwitch:
    return model_switch.ModelSwitch(
        agent_type=body.agent_type,
        connection_uid=body.connection_uid,
        model=body.model,
        effort=body.effort,
        tier_models=body.tier_models,
    )


def _file(planned: PlannedFile) -> ModelSwitchFile:
    rows = line_diff(planned.before, planned.after)
    return ModelSwitchFile(
        path=str(planned.path),
        op="add" if planned.before is None else "remove" if planned.after is None else "modify",
        added=sum(1 for r in rows if r.kind == "add"),
        removed=sum(1 for r in rows if r.kind == "remove"),
        diff=[
            ModelSwitchLine(kind=r.kind, text=r.text, old_no=r.old_no, new_no=r.new_no)
            for r in rows
        ],
        fingerprint=planned.fingerprint,
    )


def _out(result: model_switch.SwitchPreview) -> ModelSwitchOut:
    return ModelSwitchOut(
        agent_uid=result.agent_uid,
        agent_name=result.agent_name,
        connection_name=result.connection_name,
        files=[_file(f) for f in result.files],
    )


@router.post("/preview", response_model=ModelSwitchOut)
async def preview_model_switch(
    body: ModelSwitchIn,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ModelSwitchOut:
    """The files this switch would change, with their diffs; nothing is written.
    409 when the connection or agent is off or the connection does not reach the agent."""
    return _out(await model_switch.preview(svc, _switch(body)))


@router.post("/apply", response_model=ModelSwitchOut)
async def apply_model_switch(
    body: ModelSwitchIn,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    agents: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ModelSwitchOut:
    """Write the switch. 409 ``CONFIG_FILE_STALE`` when a file named in ``seen``
    changed on disk after the preview was made: nothing is written then."""
    return _out(await model_switch.apply(svc, agents, _switch(body), body.seen or {}, actor=actor))


__all__ = ["router"]
