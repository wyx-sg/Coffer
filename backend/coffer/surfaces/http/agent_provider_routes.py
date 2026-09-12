"""``/api/v1/agent-providers`` — the agents the turn platform can run a turn on.

This route outlived the web chat page it was built for. It answers "which
agents are registered" — the question the channel editor asks before binding a
channel to an agent. It has nothing to do with a conversation, so it did not
keep the old ``/api/v1/chat`` prefix.

The prefix is ``agent-providers`` rather than ``agents`` because the subject is
the ``AgentProviderRegistry`` — the adapters that can drive a turn — not the
``agent`` Resource rows that ``/api/v1/agents`` serves. Reusing that prefix
would also have put a literal path segment in front of ``/agents/{name}``.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.turn_dependencies import get_agent_registry


class AgentProviderOut(BaseModel):
    agent_key: str
    display_name: str
    available: bool


class AgentProviderListOut(BaseModel):
    agents: list[AgentProviderOut]


router = APIRouter(
    prefix="/api/v1/agent-providers",
    tags=["agent-providers"],
    dependencies=[Depends(require_token)],
)


@router.get("", response_model=AgentProviderListOut)
async def list_agent_providers(
    registry: AgentProviderRegistry = Depends(get_agent_registry),  # noqa: B008
) -> AgentProviderListOut:
    """List the registered agent providers, each with an availability flag."""
    agents: list[AgentProviderOut] = []
    for entry in registry.entries():
        available = await entry.provider.availability()
        agents.append(
            AgentProviderOut(
                agent_key=entry.provider.agent_key,
                display_name=entry.display_name,
                available=available,
            )
        )
    return AgentProviderListOut(agents=agents)
