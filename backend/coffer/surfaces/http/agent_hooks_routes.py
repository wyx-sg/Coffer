"""GET /api/v1/agents/{uid}/hooks — every hook in the agent's native config,
read only (spec agent-registry "List every hook in the agent's native config")."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.agent.hooks_service import AgentHooksService
from coffer.domain.agent.hooks import HookSource
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.agent_workspace_routes import ParseErrorOut
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workspace_dependencies import get_agent_hooks_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


class NativeHookOut(BaseModel):
    event: str
    matcher: str | None
    command: str
    type: str
    timeout: int | None
    #: Position in the file: ``hooks.<event>[group_index].hooks[hook_index]``.
    group_index: int
    hook_index: int
    #: ``user`` (a file in the agent's config dir) or ``plugin``.
    source: HookSource
    #: The file that declares the hook.
    path: str
    #: The contributing plugin's id, for a ``plugin`` hook.
    plugin: str | None


class AgentHooksOut(BaseModel):
    items: list[NativeHookOut]
    parse_errors: list[ParseErrorOut]


@router.get("/{uid}/hooks", response_model=AgentHooksOut)
async def list_agent_hooks(
    uid: str,
    svc: AgentHooksService = Depends(get_agent_hooks_service),  # noqa: B008
) -> AgentHooksOut:
    """Every hook the agent's own files and enabled plugins declare. Writes
    nothing."""
    out = await svc.list_hooks(uid)
    return AgentHooksOut(
        items=[
            NativeHookOut(
                event=h.event,
                matcher=h.matcher,
                command=h.command,
                type=h.type,
                timeout=h.timeout,
                group_index=h.group_index,
                hook_index=h.hook_index,
                source=h.source,
                path=h.path,
                plugin=h.plugin,
            )
            for h in out.items
        ],
        parse_errors=[
            ParseErrorOut(source=e.source, path=e.path, error=e.error) for e in out.parse_errors
        ],
    )
