"""The switch itself: put one agent on a connection, or back on its own
built-in login (spec provider-switching).

Both are PER AGENT. Which connection an agent runs on is a field of the agent's
own record (``AgentConfig.connection_uid``), so a switch changes that agent's
native config file and that agent's record and nothing else: no other agent type
is de-projected, no other connection loses a flag, and there is no
all-or-nothing "revert as a unit".

Each projects (or de-projects) BEFORE it touches the record, so a native-config
write that fails, or that the store refuses because the user edited the file,
leaves the registry exactly as it was — and the file is put back if the write
that follows it is the one that failed.

Lives here rather than in ``provider/service.py`` because that module is at its
file-size ceiling; ``ProviderService.activate`` / ``deactivate`` stay thin
delegates, as ``update`` and the two default flags already do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.provider.projection_ops import deproject_connection, project_connection
from coffer.application.provider.projector import Priors
from coffer.application.provider.results import ActivateResult, DeactivateResult
from coffer.application.provider.targets import connection_for_agent, reaches
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.errors import ProviderDoesNotReachAgent, ProviderInternalOnly
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


def agent_of_type(agents: list[Resource], agent_type: AgentType) -> Resource | None:
    """The registered agent of ``agent_type`` (there is at most one)."""
    for row in agents:
        try:
            if AgentConfig.model_validate(row.config).type is agent_type:
                return row
        except ValueError:
            continue
    return None


async def activate_checks(
    service: ProviderService,
    resource: Resource,
    cfg: ProviderConfig,
    agent: Resource,
    agent_type: AgentType,
) -> None:
    """Refuse a switch that cannot take effect, before anything is touched."""
    # ollama is internal-only: it reaches no agent and switching one onto it
    # writes nothing.
    if cfg.protocol is Protocol.OLLAMA:
        raise ProviderInternalOnly(resource.name)
    if not agent.enabled:
        # Coffer writes nothing into an agent the user switched off.
        raise ProviderDoesNotReachAgent(
            resource.name, agent_type.value, "the agent is switched off"
        )
    if not resource.enabled:
        raise ProviderDoesNotReachAgent(
            resource.name, agent_type.value, "the connection is switched off"
        )
    if not reaches(resource, cfg, agent):
        raise ProviderDoesNotReachAgent(
            resource.name, agent_type.value, "its scope does not name the agent"
        )


async def activate(
    service: ProviderService, uid: str, agent_type: AgentType, *, actor: str
) -> ActivateResult:
    """Make ``uid`` the connection the agent of ``agent_type`` runs on, and
    project it into that agent's native config."""
    resource = await service.get(uid)
    cfg = service._cfg(resource)
    if cfg.protocol is Protocol.OLLAMA:
        raise ProviderInternalOnly(resource.name)
    agent = agent_of_type(await service._agents.list(), agent_type)
    if agent is None:
        raise ResourceNotFound(agent_type.default_name())
    await activate_checks(service, resource, cfg, agent, agent_type)
    previous = connection_for_agent(agent, await service.list())

    # The file is the agent's own; the record write that follows could still
    # fail, and an agent pointed at the proxy with no connection behind it is
    # worse than the switch not happening.
    priors: Priors = {}
    try:
        projected = await project_connection(
            service, resource, cfg, [agent_type], [agent], actor=actor, priors=priors
        )
        await service._agents.set_connection(agent.uid, resource.uid, actor=actor)
    except Exception:
        service._projector.restore(priors)
        raise

    await service._audit.record(
        AuditEventType.PROVIDER_SWITCHED.value,
        resource=resource,
        actor=actor,
        details={
            # Labels, for a human reading the trail. The row the event belongs
            # to travels as ``resource``, so the entry stays attached to this
            # connection whatever it is later called.
            "from": previous[0].name if previous is not None else None,
            "to": resource.name,
            "protocol": cfg.protocol.value,
            "agent_type": agent_type.value,
            "agents": projected,
        },
    )
    return ActivateResult(
        activated=resource.name,
        protocol=cfg.protocol.value,
        agent_type=agent_type.value,
        agent=agent.name,
    )


async def deactivate(
    service: ProviderService, agent_type: AgentType, *, actor: str
) -> DeactivateResult:
    """Put the agent of ``agent_type`` back on its own built-in login: remove
    Coffer's keys from its native config and clear its connection. Idempotent,
    and only this agent changes."""
    agents = await service._agents.list()
    agent = agent_of_type(agents, agent_type)
    if agent is None:
        return DeactivateResult(agent_type=agent_type.value, deprojected=[], previous=None)
    chosen = AgentConfig.model_validate(agent.config).connection_uid
    # The connection the record named, even one that no longer reaches the agent
    # or is gone: the trail says what the agent was on.
    named = next((r for r in await service.list() if r.uid == chosen), None)

    priors: Priors = {}
    try:
        deprojected = await deproject_connection(
            service, agents, agent_type, actor=actor, connection=named, priors=priors
        )
        if chosen is not None:
            await service._agents.set_connection(agent.uid, None, actor=actor)
    except Exception:
        service._projector.restore(priors)
        raise

    if named is not None or deprojected:
        # Filed under the connection that was switched off, or under no resource
        # at all when there was none — which is the honest answer for "the agent
        # was already on its built-in login and Coffer's leftover keys were
        # removed".
        await service._audit.record(
            AuditEventType.PROVIDER_SWITCHED.value,
            resource=named,
            actor=actor,
            details={
                "from": named.name if named is not None else None,
                "to": None,
                "agent_type": agent_type.value,
                "agents": deprojected,
            },
        )
    return DeactivateResult(
        agent_type=agent_type.value,
        deprojected=deprojected,
        previous=named.name if named is not None else None,
    )


__all__ = ["activate", "activate_checks", "agent_of_type", "deactivate"]
