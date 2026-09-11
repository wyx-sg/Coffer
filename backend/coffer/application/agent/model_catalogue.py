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

Neither is a validator. A model NAME typed anywhere is passed to the CLI
verbatim: it accepts aliases the catalogue never carries and models newer than
the installed binary, and Coffer does not own that namespace.
"""

from __future__ import annotations

import logging
import pathlib
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


class AgentLister(Protocol):
    """The agent registry, narrowed to the one call this service needs
    (the same port ``ProviderService`` takes as ``agents``)."""

    async def list(self) -> list[Resource]: ...


class AgentModelCatalogueService:
    """The deduped view of whatever discovery reports for one agent type."""

    def __init__(self, *, agents: AgentLister, discovery: ModelDiscoveryPort) -> None:
        self._agents = agents
        self._discovery = discovery

    async def catalogue(self, agent_key: str) -> list[AgentModel]:
        """Every model ``agent_key`` can be put on, in the order discovery
        returned them, deduped by ``id`` (first occurrence wins, so the source
        that carries the better label leads)."""
        config_dir = await self._config_dir(agent_key)
        models: list[AgentModel] = []
        seen: set[str] = set()
        for found in await self._discover(agent_key, config_dir):
            if found.id in seen:
                continue
            seen.add(found.id)
            models.append(found)
        return models

    async def offered(self, agent_key: str) -> list[AgentModel]:
        """What a PICKER should show: the catalogue narrowed to the models the
        user curated, in catalogue order.

        An empty curated set means "not curated yet" and offers the whole
        catalogue. A curated id the catalogue no longer carries — a model the
        last CLI upgrade dropped, or one the retirement table now rules out — is
        simply not offered; the catalogue is the truth about what exists and
        curation only narrows it.
        """
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
