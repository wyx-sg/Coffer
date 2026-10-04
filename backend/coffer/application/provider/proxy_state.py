"""What the local model proxy serves, built from the connections and agents
(ADR api-key-providers-are-reached-through-a-separate-local-model-proxy).

The proxy holds no database; the daemon pushes it one :class:`ProxyState` —
every managed agent's token digest, and for each agent on a connection
(``AgentConfig.connection_uid``, read through ``targets.connection_for_agent``)
the members that may serve it: that connection first, then every other
enabled connection that reaches the same agent type, speaks the same protocol
and is switched on as a fallback, in Model providers list order (spec
provider-switching "Order providers, and fail over in that order"; failover
never changes the model, so the proxy uses a fallback member only for a model
it lists). A local runtime is a single member: there is nothing
local to fail over to, and a prompt meant for a local model never leaves the
machine by failing over.

Keys are decrypted here, in the daemon, the only holder of the master key,
and travel to the proxy over its authenticated loopback control route.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from coffer.application.provider.proxy_tokens import ProxyTokenService
from coffer.application.provider.targets import connection_for_agent, reaches
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.model_proxy.state import (
    ProxyAgent,
    ProxyMember,
    ProxyRoute,
    ProxyState,
    UpstreamAuth,
    upstream_root,
)
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.modality import Modality
from coffer.domain.resource import Resource
from coffer.domain.usage.records import Wire

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService

_revisions = itertools.count(1)


def _wire_for(service: ProviderService, agent_type: AgentType) -> Wire | None:
    facet = service._catalog.provider_projection(agent_type)
    if facet is None or not facet.protocols:
        return None
    try:
        return Wire(facet.protocols[0])
    except ValueError:
        return None


async def _member(
    service: ProviderService, resource: Resource, cfg: ProviderConfig, wire: Wire
) -> ProxyMember | None:
    key: str | None = None
    if cfg.secret_ref is not None:
        try:
            key = await service._key_of(cfg, label=resource.name, uid=resource.uid)
        except Exception:
            # A missing secret, or a key whose base URL nobody approved yet, is
            # no member: the proxy never holds a key it may not send.
            return None
    if key is None and not cfg.is_local:
        return None
    auth = UpstreamAuth.NONE
    if key is not None:
        auth = UpstreamAuth.ANTHROPIC if wire is Wire.ANTHROPIC else UpstreamAuth.BEARER
    return ProxyMember(
        connection_uid=resource.uid,
        connection_name=resource.name,
        upstream_root=upstream_root(cfg.base_url),
        auth=auth,
        key=key,
        models=cfg.model_ids(Modality.TEXT),
        local=cfg.is_local,
    )


async def build_proxy_state(service: ProviderService, tokens: ProxyTokenService) -> ProxyState:
    """The state to push now: every agent's token digest, and a route
    for each one that runs on a connection."""
    agents = await service._agents.list()
    enabled: list[tuple[Resource, AgentConfig]] = []
    for row in agents:
        try:
            enabled.append((row, AgentConfig.model_validate(row.config)))
        except Exception:
            continue
    # A token is kept under its agent's name; one no agent goes by any more
    # (a removed agent's) is deleted here, where every agent is in hand.
    await tokens.prune(row.name for row in agents)
    digests = await tokens.digests(row.name for row, _ in enabled)
    # Already in list order — the order fallbacks are tried in.
    connections = await service.list()

    routes: list[ProxyRoute] = []
    for row, cfg in enabled:
        wire = _wire_for(service, cfg.type)
        if wire is None:
            continue
        chosen = connection_for_agent(row, connections)
        if chosen is None:
            continue
        active, active_cfg = chosen
        primary = await _member(service, active, active_cfg, wire)
        if primary is None:
            continue
        members = [primary]
        if not active_cfg.is_local:
            for other in connections:
                other_cfg = service._cfg(other)
                if other.uid == active.uid or not other_cfg.offers_fallback:
                    continue
                if not reaches(other, other_cfg, row) or other_cfg.protocol != active_cfg.protocol:
                    continue
                member = await _member(service, other, other_cfg, wire)
                if member is not None and member.models:
                    members.append(member)
        routes.append(ProxyRoute(agent_uid=row.uid, wire=wire, members=members))

    return ProxyState(
        revision=next(_revisions),
        agents=[
            ProxyAgent(agent_uid=row.uid, agent_type=cfg.type.value, token_sha256=digests[row.name])
            for row, cfg in enabled
        ],
        routes=routes,
    )


__all__ = ["build_proxy_state"]
