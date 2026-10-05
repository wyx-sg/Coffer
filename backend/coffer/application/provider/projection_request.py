"""How a connection and an agent become a projection request (spec provider-switching).

Split from :mod:`coffer.application.provider.projector`, which orchestrates the
reads and writes; these are the pure builders it and the reconciler share.
"""

from __future__ import annotations

from coffer.domain.agent.config import AgentConfig
from coffer.domain.model_proxy.state import WIRE_PATHS
from coffer.domain.provider.agent_projection import ProviderProjectionRequest
from coffer.domain.provider.api_key_helper import proxy_token_args, proxy_token_helper
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.modality import Modality
from coffer.domain.provider.model_binding import ModelBinding, ProjectedModel
from coffer.domain.resource import Resource
from coffer.domain.usage.records import Wire


def binding_of(agent_cfg: AgentConfig) -> ModelBinding:
    """The agent's model binding, as the projection reads it."""
    return ModelBinding(
        model=agent_cfg.model,
        tier_models=dict(agent_cfg.tier_models or {}),
    )


def projected_models(cfg: ProviderConfig) -> tuple[ProjectedModel, ...]:
    """The connection's curated TEXT models with what it records about each —
    a model catalogue is the agent's own picker (spec provider-switching
    "Offer only text models to chat pickers")."""
    return tuple(
        ProjectedModel(
            id=m.id,
            context_window=m.context_window,
        )
        for m in cfg.models
        if m.modality is Modality.TEXT
    )


def projection_request(
    connection: Resource,
    cfg: ProviderConfig,
    agent: Resource,
    agent_cfg: AgentConfig,
    *,
    coffer_cli: str,
    proxy_root: str,
    wire: Wire,
) -> ProviderProjectionRequest:
    """The one construction of a projection request — what the switch writes
    and what the reconciler compares an agent's file against.

    The agent is pointed at the local model proxy's route for its wire, and
    authenticates with its own local token: the connection's endpoint and key
    stay with the proxy (ADR api-key-providers-are-reached-through-a-separate-
    local-model-proxy), so switching between two connections moves the
    proxy's route, not the agent's file.
    """
    return ProviderProjectionRequest(
        connection_uid=connection.uid,
        connection_name=connection.name,
        agent_uid=agent.uid,
        base_url=proxy_root.rstrip("/") + WIRE_PATHS[wire],
        key_helper=proxy_token_helper(agent.uid, coffer_cli=coffer_cli),
        codex_auth=CodexAuthCommand(coffer_cli, proxy_token_args(agent.uid)),
        # Model comes solely from the per-agent binding (spec
        # provider-switching "Take projected model keys from the agent's
        # binding"); an unbound agent projects no model.
        binding=binding_of(agent_cfg),
        models=projected_models(cfg),
        local=cfg.is_local,
    )


__all__ = ["binding_of", "projected_models", "projection_request"]
