"""Agent session lifecycle routes (Slice 6 FR-049).

One endpoint the installed ``coffer-hook`` calls:

- ``GET  /api/v1/agents/{name}/session-context`` — the SessionStart rules bundle
  (project + global rules + the two seeded built-in rules) to inject as
  additional context. Runtime-only; nothing is written to the agent's files.

It verifies the agent exists first (unknown agent → 404 via the agent lookup).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.knowledge.session_context import assemble_memory_digest
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_agent_service, get_knowledge_service

#: SessionStart bundles are capped by the external hook contract (≤10k chars);
#: the memory digest takes whatever budget the rules bundle leaves.
_MAX_CONTEXT_CHARS = 10_000

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class SessionContextOut(BaseModel):
    additional_context: str


@router.get("/{name}/session-context", response_model=SessionContextOut)
async def session_context(
    name: str,
    cwd: str | None = None,
    agents: Any = Depends(get_agent_service),  # noqa: B008
    memory: Any = Depends(get_knowledge_service),  # noqa: B008
) -> SessionContextOut:
    # Raises ResourceNotFound (→ 404) when the agent doesn't exist; the hook
    # swallows non-200s and injects nothing, so a 404 never blocks the agent.
    await agents.get(name)
    rules = await memory.assemble_session_context(cwd=cwd)
    # Ambient memory injection (FR-055): surface the project's knowledge index so
    # the agent starts with memory without having to call recall. Takes whatever
    # char budget the rules bundle leaves.
    digest = await assemble_memory_digest(
        cwd=cwd, memory=memory, max_chars=_MAX_CONTEXT_CHARS - len(rules) - 2
    )
    bundle = f"{rules}\n\n{digest}" if digest else rules
    return SessionContextOut(additional_context=bundle)
