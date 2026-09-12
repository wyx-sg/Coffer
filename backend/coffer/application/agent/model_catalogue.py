"""``AgentModelCatalogueService`` — the models a managed agent can be put on.

One catalogue for every surface that offers a model choice (the web picker, the
channel ``/model`` card, and the note the agent itself is told at turn time), so
they can never drift apart again.

Coffer holds no list of its own: the catalogue is whatever the injected
``ModelDiscoveryPort`` reports, which is how a model released after this build
still reaches the picker with the right version in its name. This service only
adds the things discovery cannot know: which agent's config dir to look in, a
stable dedupe so the same id offered by two sources appears once, and which
endpoint the agent's turns actually go to.

Two different answers live here, and confusing them is the bug this module is
shaped to prevent:

* ``catalogue()`` — everything the installed agent reports. It is the full
  truth, and it is what the agent detail page renders. Nothing narrows it.
* ``offered()`` / ``suggest()`` — what a PICKER should show. Usually the same
  list: the agent's catalogue is what the agent itself can run, and nothing on
  the AGENT narrows it. Curation for a given audience belongs to the surface
  that has one — a channel carries its own allowed range and applies it to its
  own ``/model`` card — not to the agent, which answers only "what can this
  agent be put on".

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
        is the full truth the agent detail page renders, and what a picker does
        with it is ``offered()``'s business.
        """
        config_dir = await self._config_dir(agent_key)
        return _deduped(await self._discover(agent_key, config_dir))

    async def offered(self, agent_key: str) -> list[AgentModel]:
        """What a PICKER should show.

        An ACTIVE connection answers outright: its curated ids ARE the list, in
        the user's order, and the agent's catalogue is not consulted. The
        catalogue describes the account the agent logs into itself, and an
        active connection means the turns do not go there — mixing the two could
        only offer ids the endpoint rejects. A connection that curates nothing
        falls through: Coffer knows where the turns go, not what that endpoint
        serves, and it will not ask over the network from a read that happens on
        every card render and every turn (CODE-034). The user closes that gap by
        curating the connection's model set.

        Otherwise: the agent's whole catalogue. Nothing narrows it — the
        catalogue is simply what the agent can be put on, and no surface that
        routes to the agent gets to say otherwise.
        """
        endpoint_models = await self._connection_models(agent_key)
        if endpoint_models:
            # No label: the id is the user's own text, and the only thing that
            # could describe it is the endpoint, which this must not ask.
            return _deduped(AgentModel(id=model_id) for model_id in endpoint_models)
        return await self.catalogue(agent_key)

    async def suggest(self, agent_key: str) -> list[str]:
        """The plain-id list — satisfies the channel ``ModelSuggestionPort``, so
        a ``/model`` card offers exactly what the web picker does. Nothing sits
        between the two: this is the whole menu a channel presents."""
        return [m.id for m in await self.offered(agent_key)]

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

        One resource answers for the type, so the catalogue of a type is always
        one agent's answer rather than a blend of several.

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
