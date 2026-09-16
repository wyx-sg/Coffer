"""``/api/v1/agent-providers`` — the agents the turn platform can run a turn on.

These two routes outlived the web chat page they were built for. They answer
"which agents are registered, and what models can each be put on" — questions
the channel editor asks before binding a channel to an agent, and the agent
detail page asks before offering a model picker. Neither has anything to do
with a conversation, so neither kept the old ``/api/v1/chat`` prefix.

The prefix is ``agent-providers`` rather than ``agents`` because the subject is
the ``AgentProviderRegistry`` — the adapters that can drive a turn — not the
``agent`` Resource rows that ``/api/v1/agents`` serves. Reusing that prefix
would also have put a literal path segment in front of ``/agents/{name}``.

The model catalogue is the agent kind's knowledge — its service reads the
agent's own executable, RPC and config — but this module belongs to the turn
platform, and the import-linter cross-kind contract forbids chat from
importing the agent kind. So the catalogue arrives through the chat kind's own
``ModelCatalogPort``: the composition root publishes the agent service into
``chat.dependencies``, and this route reads only the ``CatalogueModel`` fields
the port promises.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from coffer.application.chat.ports import ModelCatalogPort
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog


class AgentProviderOut(BaseModel):
    agent_key: str
    display_name: str
    available: bool


class AgentProviderListOut(BaseModel):
    agents: list[AgentProviderOut]


class AgentModelOut(BaseModel):
    id: str
    label: str
    description: str = ""
    #: The reasoning-effort levels this model runs at, in the agent's own order;
    #: empty for an agent that takes no such setting.
    efforts: list[str] = []
    #: The level the agent itself would use when none is chosen.
    default_effort: str | None = None


class AgentModelsOut(BaseModel):
    models: list[AgentModelOut]


def _known(registry: AgentProviderRegistry, agent_key: str) -> None:
    """404 an agent key no provider answers for.

    Raised here rather than as the domain's ``UnknownAgent`` — that error means
    "no provider for this turn" and is mapped app-wide to 400, which is the
    wrong answer for a missing subresource path.
    """
    if agent_key not in registry.agent_keys():
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_key!r}")


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


@router.get("/{agent_key}/models", response_model=AgentModelsOut)
async def list_agent_models(
    agent_key: str,
    registry: AgentProviderRegistry = Depends(get_agent_registry),  # noqa: B008
    catalogue: ModelCatalogPort = Depends(get_model_catalog),  # noqa: B008
) -> AgentModelsOut:
    """The models a picker should offer for this agent.

    On the agent's own built-in login this is whatever the agent itself reports:
    Claude Code's tier aliases, each labelled with the model it resolves to
    today; Codex's versioned ids, each carrying the reasoning-effort levels it
    can run at. An effort is not part of a model NAME — Codex takes it as its
    own field on a turn — so it rides beside the id instead of multiplying the
    list.

    With a Coffer connection ACTIVE for this agent, its curated ids are the list
    instead, in the user's own order: the turns go to that endpoint and not to
    the account the agent's own catalogue describes, so offering both could only
    offer ids the endpoint rejects. A connection that curates nothing falls back
    to the agent's catalogue — Coffer knows where the turns go, not what that
    endpoint serves, and this read never asks over the network (spec
    provider-switching FR-032). Reasoning levels survive the narrowing, because
    a level is a setting on the agent's own runtime rather than the endpoint's
    to answer.

    This is the same answer a channel's ``/model`` card gets, from the same
    function. It did not use to be: this route served the agent's whole
    catalogue and the web picker merged the endpoint's models into it in the
    browser, so the page and the chat disagreed about one question.

    An unregistered ``agent_key`` is a 404.
    """
    _known(registry, agent_key)
    models = await catalogue.offered(agent_key)
    return AgentModelsOut(
        models=[
            AgentModelOut(
                id=m.id,
                label=m.label,
                description=m.description,
                efforts=list(m.efforts),
                default_effort=m.default_effort,
            )
            for m in models
        ]
    )
