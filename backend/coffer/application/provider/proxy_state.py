"""What the local model proxy serves, built from the connections and agents
(ADR api-key-providers-are-reached-through-a-separate-local-model-proxy).

The proxy holds no database; the daemon pushes it one :class:`ProxyState` —
every managed agent's token digest, and for each agent on a connection
(``AgentConfig.connection_uid``, read through ``targets.connection_for_agent``)
the one upstream that serves it: that connection's endpoint and key.

Keys are decrypted here, in the daemon, the only holder of the master key,
and travel to the proxy over its authenticated loopback control route.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from coffer.application.provider.projector import binding_of
from coffer.application.provider.proxy_tokens import ProxyTokenService
from coffer.application.provider.targets import connection_for_agent
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
from coffer.domain.provider.agent_projection import tier_models_for
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


def _model_fallback(
    cfg: ProviderConfig, agent_cfg: AgentConfig, wire: Wire
) -> tuple[list[str], str | None, dict[str, str]]:
    """``(served ids, fallback, tier fallbacks)``: the connection's curated ids,
    the model an unserved request becomes — the agent's bound model when the
    connection serves it, else its first curated text model — and, on the
    Anthropic wire, the model projected for each Claude Code tier. No curated
    set: nothing."""
    served = cfg.model_ids()
    if not served:
        return [], None, {}
    fallback: str | None
    if agent_cfg.model in served:
        fallback = agent_cfg.model
    else:
        fallback = next(iter(cfg.model_ids(Modality.TEXT)), None)
    tiers: dict[str, str] = {}
    if wire is Wire.ANTHROPIC:
        tiers = tier_models_for(
            binding_of(agent_cfg), cfg.model_ids(Modality.TEXT), local=cfg.is_local
        )
    return served, fallback, tiers


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
        member = await _member(service, active, active_cfg, wire)
        if member is None:
            continue
        served, fallback, tiers = _model_fallback(active_cfg, cfg, wire)
        routes.append(
            ProxyRoute(
                agent_uid=row.uid,
                wire=wire,
                member=member,
                served_models=served,
                fallback_model=fallback,
                tier_fallbacks=tiers,
            )
        )

    return ProxyState(
        revision=next(_revisions),
        agents=[
            ProxyAgent(agent_uid=row.uid, agent_type=cfg.type.value, token_sha256=digests[row.name])
            for row, cfg in enabled
        ],
        routes=routes,
    )


__all__ = ["build_proxy_state"]
