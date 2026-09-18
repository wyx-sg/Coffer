"""Projection calls for ``ProviderService`` that leave a trail when refused.

The projector writes into the user's own agent config files, and the store
refuses a write when the file changed on disk between Coffer's read and its
write (``ConfigFileStale``, a 409 to the caller). That refusal is the right
outcome — the user's edit survives — but it also means an activation the user
asked for did NOT reach the agent, so it is recorded in the audit log before
the error propagates: the trail says which connection, which file, and why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import ConfigFileStale

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


async def _record_refusal(
    service: ProviderService,
    exc: ConfigFileStale,
    *,
    connection: Resource | None,
    agent_type: AgentType,
    actor: str,
) -> None:
    await service._audit.record(
        AuditEventType.PROVIDER_PROJECTION_REFUSED.value,
        # The row itself, so the event is filed under the connection's identity
        # and stays attached to it through a rename. ``None`` on the
        # de-projection path that has no connection to name: it is reverting an
        # agent to its built-in login, which is a fact about the agent's file
        # rather than about any one connection.
        resource=connection,
        actor=actor,
        details={
            # The LABEL as it stood, for a human reading the trail.
            "connection": connection.name if connection is not None else None,
            "agent_type": agent_type.value,
            "path": exc.key,
            "reason": "config file changed on disk since it was read",
        },
    )


async def project_connection(
    service: ProviderService,
    connection: Resource,
    cfg: ProviderConfig,
    targets: list[AgentType],
    agents: list[Resource],
    *,
    actor: str,
) -> list[str]:
    """Project ``connection`` into every agent of each type in ``targets``; return
    the projected agent names. A stale-file refusal is audited, then re-raised."""
    projected: list[str] = []
    for agent_type in targets:
        try:
            projected.extend(service._projector.project_type(connection, cfg, agents, agent_type))
        except ConfigFileStale as exc:
            await _record_refusal(
                service, exc, connection=connection, agent_type=agent_type, actor=actor
            )
            raise
    return projected


async def deproject_connection(
    service: ProviderService,
    agents: list[Resource],
    agent_type: AgentType,
    *,
    actor: str,
    connection: Resource | None = None,
) -> list[str]:
    """Remove Coffer's projection from every agent of ``agent_type``; return the
    reverted names. A stale-file refusal is audited, then re-raised."""
    try:
        return service._projector.deproject_type(agents, agent_type)
    except ConfigFileStale as exc:
        await _record_refusal(
            service, exc, connection=connection, agent_type=agent_type, actor=actor
        )
        raise


__all__ = ["deproject_connection", "project_connection"]
