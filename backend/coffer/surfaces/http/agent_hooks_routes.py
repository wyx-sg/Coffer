"""GET /api/v1/agents/{uid}/hooks — every hook in the agent's native config,
read only (spec agent-registry "List every hook in the agent's native config")."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.agent.hooks_service import AgentHooksService
from coffer.domain.agent.hooks import HookHealth, HookSource
from coffer.domain.hook_trust import HookTrust
from coffer.surfaces.http.agent_workspace_routes import ParseErrorOut
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.workspace_dependencies import get_agent_hooks_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class NativeHookOut(BaseModel):
    event: str
    matcher: str | None
    command: str
    type: str
    timeout: int | None
    #: ``user`` (a file in the agent's config dir) or ``plugin``.
    source: HookSource
    #: The file that declares the hook.
    path: str
    #: The contributing plugin's id, for a ``plugin`` hook.
    plugin: str | None
    #: Whether this is Coffer's own delivery hook.
    coffer: bool


class CofferHookOut(BaseModel):
    event: str
    path: str
    #: ``current`` / ``stale`` / ``missing``.
    health: HookHealth
    #: Whether the agent will run it. Codex skips a hook the user has not
    #: approved in ``/hooks`` (``untrusted``, or ``modified`` once the command
    #: changed); ``not_required`` for an agent with no review step.
    trust: HookTrust
    installed_command: str | None
    expected_command: str
    #: The last recorded fire (audit ``memory_delivery_fired``), if any.
    last_fired_at: datetime | None


class AgentHooksOut(BaseModel):
    items: list[NativeHookOut]
    #: ``None`` when the agent type has no delivery hook.
    coffer_hook: CofferHookOut | None
    parse_errors: list[ParseErrorOut]


@router.get("/{uid}/hooks", response_model=AgentHooksOut)
async def list_agent_hooks(
    uid: str,
    svc: AgentHooksService = Depends(get_agent_hooks_service),  # noqa: B008
) -> AgentHooksOut:
    """Every hook the agent's own files and enabled plugins declare, with
    Coffer's own marked and its health. Writes nothing."""
    out = await svc.list_hooks(uid)
    hook = out.coffer_hook
    return AgentHooksOut(
        items=[
            NativeHookOut(
                event=h.event,
                matcher=h.matcher,
                command=h.command,
                type=h.type,
                timeout=h.timeout,
                source=h.source,
                path=h.path,
                plugin=h.plugin,
                coffer=h.coffer,
            )
            for h in out.items
        ],
        coffer_hook=(
            CofferHookOut(
                event=hook.event,
                path=hook.path,
                health=hook.health,
                trust=hook.trust,
                installed_command=hook.installed_command,
                expected_command=hook.expected_command,
                last_fired_at=hook.last_fired_at,
            )
            if hook is not None
            else None
        ),
        parse_errors=[
            ParseErrorOut(source=e.source, path=e.path, error=e.error) for e in out.parse_errors
        ],
    )
