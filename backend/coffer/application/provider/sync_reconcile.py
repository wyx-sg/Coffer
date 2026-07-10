"""Provider projection as a sync post-import hook (spec 010 import
reconciliation).

``is_active`` rides the synced provider resource, but the projection into the
agent's native config file is a machine-local side-effect only
``ProviderService.activate``/``deactivate`` performed — so a switch made on
machine A converged B's REGISTRY while B's agents kept running on stale
config. This hook re-derives the desired projection from the converged rows
after every import and applies it idempotently: for each agent type with a
registered (thus installed — the agent import gate guarantees it) agent, the
active compatible connection is projected; a type with no active connection
is de-projected (a no-op when Coffer never touched that config).
"""

from __future__ import annotations

from typing import Protocol

from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource


class _Lister(Protocol):
    async def list(self) -> list[Resource]: ...


class ProviderProjectionReconcile:
    """Implements ``application.sync.ports.PostImportHook`` structurally."""

    kind = "provider"

    def __init__(self, providers: _Lister, agents: _Lister, projector: ProviderProjector) -> None:
        self._providers = providers
        self._agents = agents
        self._projector = projector

    async def reconcile(self) -> list[str]:
        errors: list[str] = []
        agents = await self._agents.list()
        active: dict[AgentType, tuple[str, ProviderConfig]] = {}
        for row in await self._providers.list():
            try:
                cfg = ProviderConfig.model_validate(row.config)
            except Exception as e:  # a quarantined-shape row must not kill the pass
                errors.append(f"{row.name}: {e}")
                continue
            if not cfg.is_active:
                continue
            for value in cfg.resolved_compatible_agents():
                active[AgentType(value)] = (row.name, cfg)
        for agent_type in AgentType:
            if not self._projector.agents_of_type(agents, agent_type):
                continue  # not registered here — nothing to project into
            try:
                entry = active.get(agent_type)
                if entry is not None:
                    name, cfg = entry
                    self._projector.project_type(name, cfg, agents, agent_type)
                else:
                    # No active connection for this type: converge on built-in
                    # (removes only Coffer-managed keys; no-op when absent).
                    self._projector.deproject_type(agents, agent_type)
            except Exception as e:
                errors.append(f"{agent_type.value}: {e}")
        return errors
