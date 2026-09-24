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

* ``catalogue()`` — everything the installed agent reports about its OWN login.
  It is the full truth and nothing narrows it, which is also why no picker reads
  it directly: ``offered()`` is the only way out to a surface.
* ``offered()`` / ``suggest()`` — what a PICKER should show. Usually the same
  list: the agent's catalogue is what the agent itself can run, and nothing
  narrows it — not the agent, and not the surface doing the asking. Curation
  lived on the agent once and on the channel after that; migration 0068 took the
  last of it away, so the web picker and a channel's ``/model`` card both offer
  the whole list.

  With an LLM connection ACTIVE for the agent, the IDS come from somewhere else
  entirely. The agent's turns then go to that endpoint, not to the account its
  own catalogue describes, so its models are the wrong list: offering them can
  only produce ids the endpoint rejects. The connection's own curated set is the
  answer instead. What the agent still answers for is the reasoning LEVELS an id
  can be run at — those belong to the runtime driving the turn, not to the
  endpoint it points at.

* ``efforts()`` — the levels for ONE chosen model, the second half of the same
  choice, asked by the web effort picker and the channel `/effort` card.

Neither is a validator. A model NAME typed anywhere is passed to the CLI
verbatim: it accepts aliases the catalogue never carries and models newer than
the installed binary, and Coffer does not own that namespace.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Iterable
from dataclasses import replace
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.model_catalogue import AgentModel
from coffer.domain.resource import Resource

_log = logging.getLogger(__name__)


class ModelDiscoveryPort(Protocol):
    """Asks an agent what models it can run.

    Async because the implementations do real I/O — scanning a CLI binary,
    driving a JSON-RPC subprocess — and a model picker must not block the
    daemon's event loop while they do.

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

    Two answers, and the difference between them is the whole point:

      * ``None`` — no restriction: no active connection is compatible with
        this agent type (the agent runs on its own login and its own catalogue
        is the truth), or one is active but curates nothing — Coffer knows
        which endpoint the turns go to, not what it serves.
      * ``[ids]`` — exactly the ``text`` ids ticked on that connection's detail
        page, in that order. EMPTY when the connection curates something but
        nothing ``text``: its chat pickers then offer nothing (spec
        provider-switching "Offer only text models to chat pickers").

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


#: The suffix Claude Code puts on a model id to run it with a 1M-token context.
_ONE_M_SUFFIX = "[1m]"


def _button_label(model: AgentModel) -> str:
    """The short name a card button shows for ``model``."""
    label = model.label or model.id
    if model.id.endswith(_ONE_M_SUFFIX) and "1M" not in label:
        label = f"{label} 1M"
    return label


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
        is the full truth, and what a picker is shown of it is ``offered()``'s
        business — including the levels ``offered()`` carries back across a
        connection's ids.
        """
        config_dir = await self._config_dir(agent_key)
        return _deduped(await self._discover(agent_key, config_dir))

    async def offered(self, agent_key: str) -> list[AgentModel]:
        """What a PICKER should show — every one of them, wherever it renders.

        Served to the web pickers over ``GET
        /api/v1/agent-providers/{agent_key}/models`` (the chat kind takes this
        method as its ``ModelCatalogPort``) and read in-process by a channel's
        ``/model`` and ``/effort`` cards, so the two cannot answer differently.

        An ACTIVE connection answers outright: its curated ids ARE the list, in
        the user's order, and the agent's catalogue is not consulted. The
        catalogue describes the account the agent logs into itself, and an
        active connection means the turns do not go there — mixing the two could
        only offer ids the endpoint rejects — so one that curates only non-text
        models offers nothing. A connection that curates nothing at all
        falls through: Coffer knows where the turns go, not what that endpoint
        serves, and it will not ask over the network from a read that happens on
        every card render and every turn. The user closes that gap by
        curating the connection's model set.

        Otherwise: the agent's whole catalogue. Nothing narrows it — the
        catalogue is simply what the agent can be put on, and no surface that
        routes to the agent gets to say otherwise.
        """
        endpoint_models = await self._connection_models(agent_key)
        if endpoint_models is not None:
            # No label: the id is the user's own text, and the only thing that
            # could describe it is the endpoint, which this must not ask.
            #
            # The reasoning LEVELS do come across, though, because they are not
            # the endpoint's to answer: the level is a setting on the agent's own
            # runtime (Codex's turn field, Claude's ``--effort``), and the turn
            # still goes through that runtime whatever endpoint it points at. An
            # id the agent also knows therefore keeps its menu; one the agent has
            # never heard of reports none, which is the honest answer. Dropping
            # them here silently emptied the effort picker for every agent the
            # moment a connection went active.
            known = {m.id: m for m in await self.catalogue(agent_key)}
            return _deduped(
                replace(known[model_id], label="", description="")
                if model_id in known
                else AgentModel(id=model_id)
                for model_id in endpoint_models
            )
        return await self.catalogue(agent_key)

    async def efforts(self, agent_key: str, model: str | None) -> list[str]:
        """The reasoning levels the conversation's CURRENT model can be run at.

        Satisfies the channel ``ModelSuggestionPort``, so an `/effort` card
        offers exactly what the web picker beside the model does — including the
        rule for "no model pinned": the agent then runs a default it never names
        to us, so the FIRST offered entry stands in for it. That stand-in could
        only mislead for an agent whose catalogue mixed effort-bearing and
        effort-free models, and neither does — Codex reports levels per model
        but for all of them, and Claude Code's are the runtime's, identical on
        every entry.

        Empty for an agent that takes no such setting, which is what a surface
        reads as "offer no control at all".
        """
        offered = await self.offered(agent_key)
        entry = next((m for m in offered if m.id == model), None) if model else None
        if entry is None and not model:
            entry = offered[0] if offered else None
        return list(entry.efforts) if entry is not None else []

    async def suggest(self, agent_key: str) -> list[str]:
        """The plain-id list — satisfies the channel ``ModelSuggestionPort``, so
        a ``/model`` card offers exactly what the web picker does. Nothing sits
        between the two: this is the whole menu a channel presents."""
        return [m.id for m in await self.offered(agent_key)]

    async def model_labels(self, agent_key: str) -> dict[str, str]:
        """``{id: button text}`` for a channel's ``/model`` card — satisfies the
        channel ``ModelSuggestionPort``. The text is the model's name, falling
        back to its id when the source gave none, with the 1M-context variant
        spelled out: Claude Code's cache labels ``claude-fable-5-1[1m]`` just
        "Fable", which beside the ``fable`` alias would read as a duplicate."""
        return {m.id: _button_label(m) for m in await self.offered(agent_key)}

    # --- internals -----------------------------------------------------------

    async def _connection_models(self, agent_key: str) -> list[str] | None:
        """The active compatible connection's curated ``text`` ids, or ``None``
        when there is no such connection (or it restricts nothing). Belt-and-
        braces around the port's never-raise contract."""
        if self._provider_models is None:
            return None
        try:
            models = await self._provider_models.curated_models(agent_key)
        except Exception:
            _log.debug("agent.provider_models.failed", exc_info=True)
            return None
        return None if models is None else list(models)

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
