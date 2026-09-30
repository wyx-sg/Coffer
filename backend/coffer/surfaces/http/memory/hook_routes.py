"""``POST /api/v1/memory/hook`` — one fire of Coffer's memory hook.

The route an installed hook reaches on every event it sits on: session start,
each prompt, and before and after each shell command (ADR
memory-reaches-a-session-at-prompt-time-and-before-a-known-trap). It answers
with the JSON the agent should read, or ``output: null`` for nothing. The
caller — ``coffer memory hook`` — prints ``output`` verbatim and fails open:
when this route cannot be reached in time, the agent gets nothing and nothing
is blocked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.hook_service import HookEvent, MemoryHookService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.memory.delivery_schemas import HookFireIn, HookFireOut
from coffer.surfaces.http.memory.dependencies import get_memory_hook_service

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


@router.post("/hook", response_model=HookFireOut)
async def hook_fire(
    body: HookFireIn,
    svc: MemoryHookService = Depends(get_memory_hook_service),  # noqa: B008
) -> HookFireOut:
    """Answer one hook fire; every fire that delivers something is audited."""
    output = await svc.handle(
        body.agent_uid,
        HookEvent(
            event=body.event,
            session_id=body.session_id,
            cwd=body.cwd,
            prompt=body.prompt,
            tool_name=body.tool_name,
            command=body.command,
            output=body.output,
        ),
    )
    return HookFireOut(output=output)
