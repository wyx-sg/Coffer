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

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.agent.service import AgentService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import get_agent_service
from coffer.surfaces.http.turn_dependencies import (
    get_agent_model_catalogue,
    get_agent_registry,
)


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


class AgentModelsOut(BaseModel):
    models: list[AgentModelOut]


class AgentModelSelectionIn(BaseModel):
    """The curated set, replaced wholesale. ``[]`` clears the curation."""

    models: list[str]


class AgentModelSelectionOut(BaseModel):
    """Which of the catalogue this agent's pickers offer.

    Separate from the catalogue on purpose: the UI needs BOTH to render a
    catalogue with ticks against it. ``models`` empty means NOT CURATED — every
    model in the catalogue is offered — never "no models".
    """

    models: list[str]


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
    catalogue: AgentModelCatalogueService = Depends(get_agent_model_catalogue),  # noqa: B008
) -> AgentModelsOut:
    """The models this agent can be put on, as the agent itself reports them.

    Concrete models only. The CLIs' tier aliases (``sonnet``, ``opus``,
    ``best``, ``sonnet[1m]``, …) are not listed: each resolves to a model that
    already appears here, so listing both filled the picker with label-less
    duplicates. An alias can still be TYPED wherever a model name is accepted.

    The list is NOT narrowed by the user's curated selection: this route is what
    the curation screen renders, so it has to show the models that are off as
    well as the ones that are on. ``GET …/models/selection`` says which are on.

    An unregistered ``agent_key`` is a 404.
    """
    _known(registry, agent_key)
    models = await catalogue.catalogue(agent_key)
    return AgentModelsOut(
        models=[AgentModelOut(id=m.id, label=m.label, description=m.description) for m in models]
    )


@router.get("/{agent_key}/models/selection", response_model=AgentModelSelectionOut)
async def get_agent_model_selection(
    agent_key: str,
    registry: AgentProviderRegistry = Depends(get_agent_registry),  # noqa: B008
    catalogue: AgentModelCatalogueService = Depends(get_agent_model_catalogue),  # noqa: B008
) -> AgentModelSelectionOut:
    """Which models this agent's pickers offer, out of the catalogue above.

    The catalogue an agent reports is CUMULATIVE — it names every model the
    installed release has heard of, including ones this account is not entitled
    to run. Which ones those are is a server-side account fact with no local
    copy, and no field of the catalogue separates them, so the user says. This
    route is their answer; the catalogue route stays the full list so the UI can
    show what is on offer and what is not.

    An empty list means NOT CURATED: every model is offered, which is how an
    agent nobody has touched behaves.
    """
    _known(registry, agent_key)
    return AgentModelSelectionOut(models=await catalogue.selection(agent_key))


@router.put("/{agent_key}/models/selection", response_model=AgentModelSelectionOut)
async def set_agent_model_selection(
    agent_key: str,
    body: AgentModelSelectionIn,
    registry: AgentProviderRegistry = Depends(get_agent_registry),  # noqa: B008
    catalogue: AgentModelCatalogueService = Depends(get_agent_model_catalogue),  # noqa: B008
    agents: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentModelSelectionOut:
    """Replace the curated set. ``[]`` clears it, restoring the whole catalogue.

    Ids are stored verbatim and are NOT checked against the catalogue: the
    catalogue moves on every CLI upgrade, and an id the current release dropped
    is a stale menu entry rather than a config error. A 404 when no agent of
    this type is registered — the set lives in that agent's config, so without
    one there is nowhere to put it.
    """
    _known(registry, agent_key)
    name = await catalogue.selection_owner(agent_key)
    if name is None:
        raise HTTPException(status_code=404, detail=f"no registered agent of type {agent_key!r}")
    await agents.set_offered_models(name=name, model_ids=body.models, actor=actor)
    return AgentModelSelectionOut(models=await catalogue.selection(agent_key))
