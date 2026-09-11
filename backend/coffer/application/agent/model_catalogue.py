"""``AgentModelCatalogueService`` — the models a managed agent can be put on.

One catalogue for every surface that offers a model choice (the web picker, the
channel ``/model`` card, and the note the agent itself is told at turn time), so
they can never drift apart again.

Coffer holds no list of its own: the catalogue is whatever the injected
``ModelDiscoveryPort`` reports, which is how a model released after this build
still reaches the picker with the right version in its name. This service only
adds the things discovery cannot know: which agent's config dir to look in, a
stable dedupe so the same id offered by two sources appears once, and the
user's own curation.

Two different answers live here, and confusing them is the bug this module is
shaped to prevent:

* ``catalogue()`` — everything the installed agent reports. It is the full
  truth, and it is what the agent detail page renders so the user can tick
  things in it. Nothing narrows it.
* ``offered()`` / ``suggest()`` — what a PICKER should show. The catalogue is
  cumulative and account-blind: it names models this account may not be
  entitled to run, and no local fact separates those from the ones that work
  (pricing, capabilities, cutoff and version number were all checked and none
  of them do). So the user ticks the ones that work, and these two narrow to
  that set. An EMPTY set means "not curated yet" and offers everything — Coffer
  must work out of the box for someone who never opens the screen.

  With an LLM connection ACTIVE for the agent, they answer from somewhere else
  entirely. The agent's turns then go to that endpoint, not to the account its
  own catalogue describes, so its models are the wrong list: offering them can
  only produce ids the endpoint rejects. The connection's own curated set is
  the answer instead, and the agent is not consulted at all.

Neither is a validator. A model NAME typed anywhere is passed to the CLI
verbatim: it accepts aliases the catalogue never carries and models newer than
the installed binary, and Coffer does not own that namespace.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Iterable
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.model_catalogue import AgentModel
from coffer.domain.resource import Resource

_log = logging.getLogger(__name__)


class ModelDiscoveryPort(Protocol):
    """Asks an agent what models it can run.

    Async because the implementations do real I/O — scanning a CLI binary,
    driving a JSON-RPC subprocess — and a model picker must not block the
    daemon's event loop while they do (CODE-034).

    ``config_dir`` is ``None`` when no agent of this type is registered with
    Coffer; sources that need it return nothing, sources that interrogate the
    installed CLI directly still answer.

    Best-effort by contract: a missing binary, an unreadable config, a CLI that
    is not logged in or does not answer are all ordinary states of the world, so
    an implementation MUST return an empty list rather than raise.
    """

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]: ...


class ActiveProviderModelsPort(Protocol):
    """The curated model set of the LLM connection Coffer has ACTIVATED for an
    agent type — the provider kind narrowed to the one question this service
    asks of it, so the agent side never imports it.

    Three answers, and the difference between the last two is the whole point:

      * ``None`` — no active connection is compatible with this agent type. The
        agent runs on its own login and its own catalogue is the truth.
      * ``[]`` — a connection is active but curates nothing ("no restriction"):
        Coffer knows which endpoint the turns go to, not what it serves.
      * ``[ids]`` — exactly the ids ticked on that connection's detail page, in
        that order.

    Best-effort by contract, like ``ModelDiscoveryPort``: an unparseable row is
    an ordinary state of the world, and a read-only picker lookup must not fail
    because of one, so an implementation MUST answer rather than raise.
    """

    async def curated_models(self, agent_key: str) -> list[str] | None: ...


class AgentLister(Protocol):
    """The agent registry, narrowed to the one call this service needs
    (the same port ``ProviderService`` takes as ``agents``)."""

    async def list(self) -> list[Resource]: ...


def _deduped(found: Iterable[AgentModel]) -> list[AgentModel]:
    """In the order given, deduped by ``id`` — first occurrence wins, so the
    source that carries the better label leads."""
    models: list[AgentModel] = []
    seen: set[str] = set()
    for model in found:
        if model.id in seen:
            continue
        seen.add(model.id)
        models.append(model)
    return models


class AgentModelCatalogueService:
    """The deduped view of whatever discovery reports for one agent type."""

    def __init__(
        self,
        *,
        agents: AgentLister,
        discovery: ModelDiscoveryPort,
        provider_models: ActiveProviderModelsPort | None = None,
    ) -> None:
        self._agents = agents
        self._discovery = discovery
        # ``None`` means no provider layer is wired into this composition (a CLI
        # one-off, a test): every agent then looks like one on its own login.
        self._provider_models = provider_models

    async def catalogue(self, agent_key: str) -> list[AgentModel]:
        """Every model ``agent_key`` can be put on, in the order discovery
        returned them, deduped by ``id`` (first occurrence wins, so the source
        that carries the better label leads).

        Always the AGENT's own answer, even while a connection is active: this
        is the full truth the detail page renders for ticking, and what a picker
        does with it is ``offered()``'s business.
        """
        config_dir = await self._config_dir(agent_key)
        return _deduped(await self._discover(agent_key, config_dir))

    async def offered(self, agent_key: str) -> list[AgentModel]:
        """What a PICKER should show.

        An ACTIVE connection answers outright: its curated ids ARE the list, in
        the user's order, and neither the agent's catalogue nor the per-agent
        selection over it is consulted. Both describe the account the agent logs
        into itself, and an active connection means the turns do not go there —
        mixing the two could only offer ids the endpoint rejects. A connection
        that curates nothing falls through: Coffer knows where the turns go, not
        what that endpoint serves, and it will not ask over the network from a
        read that happens on every card render and every turn (CODE-034). The
        user closes that gap by curating the connection's model set.

        Otherwise: the agent's catalogue narrowed to the models the user ticked,
        in catalogue order. An empty set means "not curated yet" and offers the
        whole catalogue. A curated id the catalogue no longer carries — a model
        the last CLI upgrade dropped, or one the retirement table now rules out —
        is simply not offered; the catalogue is the truth about what exists and
        curation only narrows it.
        """
        endpoint_models = await self._connection_models(agent_key)
        if endpoint_models:
            # No label: the id is the user's own text, and the only thing that
            # could describe it is the endpoint, which this must not ask.
            return _deduped(AgentModel(id=model_id) for model_id in endpoint_models)
        models = await self.catalogue(agent_key)
        chosen = set(await self.selection(agent_key))
        if not chosen:
            return models
        return [m for m in models if m.id in chosen]

    async def suggest(self, agent_key: str) -> list[str]:
        """The plain-id list — satisfies the channel ``ModelSuggestionPort`` so
        the ``/model`` card offers exactly what the web picker offers."""
        return [m.id for m in await self.offered(agent_key)]

    async def selection(self, agent_key: str) -> list[str]:
        """The ids the user curated for this agent type, or ``[]`` when they
        have curated nothing (or no agent of this type is registered)."""
        agent = await self._agent(agent_key)
        if agent is None:
            return []
        return list(AgentConfig.model_validate(agent.config).models)

    async def selection_owner(self, agent_key: str) -> str | None:
        """The name of the agent resource whose config holds the curated set —
        what a writer needs, since the set is stored per resource but addressed
        per agent TYPE (a ``/model`` card knows only the type).

        ``None`` when no agent of this type is registered, which is the one case
        a caller has to handle: there is nowhere to put the answer.
        """
        agent = await self._agent(agent_key)
        return None if agent is None else agent.name

    # --- internals -----------------------------------------------------------

    async def _connection_models(self, agent_key: str) -> list[str]:
        """The active compatible connection's curated ids, or ``[]`` when there
        is no such connection (or it restricts nothing). Belt-and-braces around
        the port's never-raise contract."""
        if self._provider_models is None:
            return []
        try:
            return list(await self._provider_models.curated_models(agent_key) or [])
        except Exception:
            _log.debug("agent.provider_models.failed", exc_info=True)
            return []

    async def _agent(self, agent_key: str) -> Resource | None:
        """The first ENABLED agent resource of this type, or ``None``.

        One resource answers for the type, and it is the SAME one for the config
        dir and for the curated set — so the catalogue and the curation over it
        can never come from two different agents.

        Disabled agents are skipped: the user has told Coffer to leave them
        alone, so their config should not feed the picker either.
        """
        for resource in await self._agents.list():
            if not resource.enabled:
                continue
            try:
                cfg = AgentConfig.model_validate(resource.config)
            except ValueError:
                # A row Coffer can no longer parse is not a reason to fail a
                # read-only catalogue lookup; the agent routes surface it.
                continue
            if cfg.type.value == agent_key:
                return resource
        return None

    async def _config_dir(self, agent_key: str) -> pathlib.Path | None:
        """The config dir of the agent answering for this type, or ``None`` when
        the user has not registered one."""
        agent = await self._agent(agent_key)
        if agent is None:
            return None
        return AgentConfig.model_validate(agent.config).resolved_config_dir()

    async def _discover(self, agent_key: str, config_dir: pathlib.Path | None) -> list[AgentModel]:
        """Belt-and-braces around the port's never-raise contract — a picker
        must never 500 because a CLI is odd today."""
        try:
            return await self._discovery.discover(agent_key=agent_key, config_dir=config_dir)
        except Exception:
            _log.debug("agent.model_discovery.failed", exc_info=True)
            return []


__all__ = ["AgentLister", "AgentModelCatalogueService", "ModelDiscoveryPort"]
