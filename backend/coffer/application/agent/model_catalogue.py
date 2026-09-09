"""``AgentModelCatalogueService`` — the models a managed agent can be put on.

One catalogue for every surface that offers a model choice (the web picker, the
channel ``/model`` card, and the note the agent itself is told at turn time), so
they can never drift apart again. The list is the curated alias table plus
whatever the agent's own config file advertises, which is how a brand-new model
reaches the picker without a Coffer release.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.model_catalogue import AgentModel, curated_for
from coffer.domain.resource import Resource

_log = logging.getLogger(__name__)


class ModelDiscoveryPort(Protocol):
    """Reads extra models out of an agent's own config dir.

    Best-effort by contract: a missing, unreadable or malformed config is the
    normal case (the user may never have opened the CLI), so an implementation
    MUST return an empty list rather than raise.
    """

    def discover(self, *, agent_key: str, config_dir: pathlib.Path) -> list[AgentModel]: ...


class AgentLister(Protocol):
    """The spec-004 agent registry, narrowed to the one call this service needs
    (the same port ``ProviderService`` takes as ``agents``)."""

    async def list(self) -> list[Resource]: ...


class AgentModelCatalogueService:
    """Merges the curated alias table with the models discovered on disk."""

    def __init__(self, *, agents: AgentLister, discovery: ModelDiscoveryPort) -> None:
        self._agents = agents
        self._discovery = discovery

    async def catalogue(self, agent_key: str) -> list[AgentModel]:
        """Every model ``agent_key`` can be put on: the curated aliases first
        (stable, human-ordered), then anything discovered that is not already
        there. Deduped by ``id``, curated wins so its label survives."""
        models = list(curated_for(agent_key))
        config_dir = await self._config_dir(agent_key)
        if config_dir is None:
            # No agent of this type is registered, so there is no config dir to
            # read — the curated aliases are the whole catalogue.
            return models
        seen = {m.id for m in models}
        for found in self._discover(agent_key, config_dir):
            if found.id in seen:
                continue
            seen.add(found.id)
            models.append(found)
        return models

    async def suggest(self, agent_key: str) -> list[str]:
        """The plain-id list — satisfies the channel ``ModelSuggestionPort`` so
        the ``/model`` card offers exactly the same catalogue as the web UI."""
        return [m.id for m in await self.catalogue(agent_key)]

    # --- internals -----------------------------------------------------------

    async def _config_dir(self, agent_key: str) -> pathlib.Path | None:
        """The config dir of the first ENABLED agent resource of this type.

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
                return cfg.resolved_config_dir()
        return None

    def _discover(self, agent_key: str, config_dir: pathlib.Path) -> list[AgentModel]:
        """Belt-and-braces around the port's never-raise contract — a picker
        must never 500 because an agent's config file is odd today."""
        try:
            return self._discovery.discover(agent_key=agent_key, config_dir=config_dir)
        except Exception:
            _log.debug("agent.model_discovery.failed", exc_info=True)
            return []


__all__ = ["AgentLister", "AgentModelCatalogueService", "ModelDiscoveryPort"]
