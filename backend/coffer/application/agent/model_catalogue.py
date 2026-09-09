"""``AgentModelCatalogueService`` — the models a managed agent can be put on.

One catalogue for every surface that offers a model choice (the web picker, the
channel ``/model`` card, and the note the agent itself is told at turn time), so
they can never drift apart again.

Coffer holds no list of its own: the catalogue is whatever the injected
``ModelDiscoveryPort`` reports, which is how a model released after this build
still reaches the picker with the right version in its name. This service only
adds the two things discovery cannot know: which agent's config dir to look in,
and a stable dedupe so the same id offered by two sources appears once.
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
    """The spec-004 agent registry, narrowed to the one call this service needs
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

    async def suggest(self, agent_key: str) -> list[str]:
        """The plain-id list — satisfies the channel ``ModelSuggestionPort`` so
        the ``/model`` card offers exactly the same catalogue as the web UI."""
        return [m.id for m in await self.catalogue(agent_key)]

    # --- internals -----------------------------------------------------------

    async def _config_dir(self, agent_key: str) -> pathlib.Path | None:
        """The config dir of the first ENABLED agent resource of this type, or
        ``None`` when the user has not registered one.

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

    async def _discover(self, agent_key: str, config_dir: pathlib.Path | None) -> list[AgentModel]:
        """Belt-and-braces around the port's never-raise contract — a picker
        must never 500 because a CLI is odd today."""
        try:
            return await self._discovery.discover(agent_key=agent_key, config_dir=config_dir)
        except Exception:
            _log.debug("agent.model_discovery.failed", exc_info=True)
            return []


__all__ = ["AgentLister", "AgentModelCatalogueService", "ModelDiscoveryPort"]
