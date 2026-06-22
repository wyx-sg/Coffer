"""Agent session lifecycle routes (Slice 6 FR-049/FR-051).

Two endpoints the installed ``coffer-hook`` calls:

- ``GET  /api/v1/agents/{name}/session-context`` — the SessionStart rules bundle
  (project + global rules + the two seeded built-in rules) to inject as
  additional context. Runtime-only; nothing is written to the agent's files.
- ``POST /api/v1/agents/{name}/sessions/{session_id}/end`` — on SessionEnd,
  distill that single session into the journal lane (idempotent; reuses the
  FR-046 ledger). A no-internal-engine / unknown-session / not-a-git-project
  session is a tolerated no-op (still 2xx) — the hook must never block the agent.

Both verify the agent exists first (unknown agent → 404 via the agent lookup).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.distill.session_end import SessionEndDistiller, SessionEndOutcome
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_memory_service,
    get_session_end_distiller,
)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class SessionContextOut(BaseModel):
    additional_context: str


class SessionEndBody(BaseModel):
    cwd: str | None = None


class SessionEndOut(BaseModel):
    outcome: str


@router.get("/{name}/session-context", response_model=SessionContextOut)
async def session_context(
    name: str,
    cwd: str | None = None,
    agents: Any = Depends(get_agent_service),  # noqa: B008
    memory: Any = Depends(get_memory_service),  # noqa: B008
) -> SessionContextOut:
    # Raises ResourceNotFound (→ 404) when the agent doesn't exist; the hook
    # swallows non-200s and injects nothing, so a 404 never blocks the agent.
    await agents.get(name)
    bundle = await memory.assemble_session_context(cwd=cwd)
    return SessionContextOut(additional_context=bundle)


@router.post("/{name}/sessions/{session_id}/end", response_model=SessionEndOut)
async def session_end(
    name: str,
    session_id: str,
    body: SessionEndBody,
    agents: Any = Depends(get_agent_service),  # noqa: B008
    distiller: SessionEndDistiller = Depends(get_session_end_distiller),  # noqa: B008
) -> SessionEndOut:
    # Unknown agent → 404; otherwise always 200 with the (idempotent) outcome.
    await agents.get(name)
    outcome: SessionEndOutcome = await distiller.distill_session(
        agent_name=name, session_id=session_id
    )
    return SessionEndOut(outcome=outcome.value)
