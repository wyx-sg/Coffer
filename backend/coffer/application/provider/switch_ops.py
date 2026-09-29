"""The switch itself: activate one connection, or put an agent back on its own
built-in login (spec provider-switching).

Both halves of one invariant — at most one active connection PER AGENT TYPE —
so they live together rather than beside the CRUD they are not. Each projects
(or de-projects) BEFORE it touches the ``is_active`` flag, so a native-config
write that fails, or that the store refuses because the user edited the file,
leaves the registry exactly as it was.

Lives here rather than in ``provider/service.py`` because that module is at its
file-size ceiling; ``ProviderService.activate`` / ``deactivate`` stay thin
delegates, as ``update`` and the two default flags already do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.provider.projection_ops import deproject_connection, project_connection
from coffer.application.provider.results import ActivateResult, DeactivateResult
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.errors import ProviderInternalOnly
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def activate(service: ProviderService, uid: str, *, actor: str) -> ActivateResult:
    """Make this the active connection for each agent its scope reaches, and
    project it into every enabled agent of those types."""
    resource = await service.get(uid)
    cfg = service._cfg(resource)
    # ollama is internal-only: it reaches no agent, is never ``is_active`` and
    # activating it writes nothing. Refused before anything is touched, so no
    # other connection is switched off on its behalf either.
    if cfg.protocol is Protocol.OLLAMA:
        raise ProviderInternalOnly(resource.name)
    agents = await service._agents.list()
    targets = service._compat(resource, agents)

    # 1) Project first. ``skipped`` lists in-scope agents with no registered one.
    projected = await project_connection(service, resource, cfg, targets, agents, actor=actor)
    covered = {at for at in targets if service._projector.agents_of_type(agents, at)}
    skipped = [at.value for at in targets if at not in covered]

    # 2) Flip activation: take over from any overlapping active connection,
    #    de-projecting it from the agents this one will not cover. The
    #    single-process daemon serialises the clear-then-set (spec
    #    provider-switching "Keep at most one active connection per agent type").
    mine = set(targets)
    previous: str | None = None
    for r in await service.list():
        # By uid: "is this the row I am activating" is an identity question, and
        # two connections may exchange names between two reads.
        if r.uid == resource.uid:
            continue
        rc = service._cfg(r)
        other = set(service._compat(r, agents))
        if not rc.is_active or not (other & mine):
            continue
        for at in other - mine:
            await deproject_connection(service, agents, at, actor=actor, connection=r)
        await service._set_active(r, active=False, actor=actor)
        previous = r.name
    if not cfg.is_active:
        await service._set_active(resource, active=True, actor=actor)

    await service._audit.record(
        AuditEventType.PROVIDER_SWITCHED.value,
        resource=resource,
        actor=actor,
        details={
            # Labels, for a human reading the trail. The row the event belongs
            # to travels as ``resource``, so the entry stays attached to this
            # connection whatever it is later called.
            "from": previous,
            "to": resource.name,
            "protocol": cfg.protocol.value,
            "agents": projected,
        },
    )
    return ActivateResult(
        activated=resource.name,
        protocol=cfg.protocol.value,
        projected=projected,
        skipped=skipped,
    )


async def deactivate(
    service: ProviderService, agent_type: AgentType, *, actor: str
) -> DeactivateResult:
    """Put every agent of ``agent_type`` back on its own built-in login.

    Named by agent, not by wire: which agents a connection reaches is its
    scope, so no protocol stands for an agent. The active connection covering
    this type is switched off as a unit — its single ``is_active`` flag is
    all-or-nothing — so it is also de-projected from the other types it reached.
    """
    agents = await service._agents.list()
    previous: Resource | None = None
    deprojected = await deproject_connection(service, agents, agent_type, actor=actor)
    for r in await service.list():
        rc = service._cfg(r)
        compat = service._compat(r, agents)
        if not rc.is_active or agent_type not in compat:
            continue
        for at in compat:
            if at is not agent_type:
                await deproject_connection(service, agents, at, actor=actor, connection=r)
        await service._set_active(r, active=False, actor=actor)
        previous = r

    if previous is not None or deprojected:
        # Filed under the connection that was switched off, or under no resource
        # at all when there was none — which is the honest answer for "the agent
        # was already on its built-in login and Coffer's leftover keys were
        # removed". The old code invented a ref naming the WIRE there, which
        # read like a resource and was not one.
        await service._audit.record(
            AuditEventType.PROVIDER_SWITCHED.value,
            resource=previous,
            actor=actor,
            details={
                "from": previous.name if previous is not None else None,
                "to": None,
                "agent_type": agent_type.value,
                "agents": deprojected,
            },
        )
    return DeactivateResult(
        agent_type=agent_type.value,
        deprojected=deprojected,
        previous=previous.name if previous is not None else None,
    )


__all__ = ["activate", "deactivate"]
