"""The per-kind sources of the Overview's "needs you" list, composed.

Each kind owns its own :class:`~coffer.application.attention.AttentionSource`
and declares the ports it reads; this is where those ports are met with the
concrete services, which is why only the composition root may import every
kind at once.

A dependency that is ``None`` — a daemon wired without it — leaves its source
out rather than failing the list: a source that cannot be asked would only
ever report its own error.
"""

from __future__ import annotations

from coffer.application.agent.attention import AgentAttentionSource
from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.connection_service import AgentConnectionService
from coffer.application.attention import AttentionSource
from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.channel.service import ChannelService
from coffer.application.mcp.attention import McpAttentionSource
from coffer.application.resource_service import ResourceService
from coffer.application.sync.attention import SyncAttentionSource
from coffer.application.sync.service import ConvergeService
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.mcp.health_repo import MCPServerHealthRepo


def build_attention_sources(
    *,
    resource_svc: ResourceService,
    credential_store: EncryptedCredentialStore,
    connection_service: AgentConnectionService,
    auto_detect: AutoDetectService,
    sync_service: ConvergeService | None,
    channel_service: ChannelService | None,
    health_repo: MCPServerHealthRepo | None,
) -> list[AttentionSource]:
    """Every kind's source, in the order the Overview groups them."""
    sources: list[AttentionSource] = []
    if health_repo is not None:
        sources.append(
            McpAttentionSource(
                resources=resource_svc, health=health_repo, credentials=credential_store
            )
        )
    sources.append(
        AgentAttentionSource(agents=resource_svc, detect=auto_detect, connection=connection_service)
    )
    if channel_service is not None:
        sources.append(ChannelAttentionSource(resources=resource_svc, channels=channel_service))
    if sync_service is not None:
        sources.append(SyncAttentionSource(sync=sync_service))
    return sources


def lifespan_attention_sources(
    *,
    resource_svc: ResourceService,
    credential_store: EncryptedCredentialStore,
    connection_service: AgentConnectionService,
    sync_service: ConvergeService | None,
) -> list[AttentionSource]:
    """:func:`build_attention_sources` with the services the kinds published
    while they were wired (the channel service, the agent detector, the MCP
    health store) looked up where they were published."""
    from coffer.surfaces.http.agent_dependencies import get_auto_detect_service
    from coffer.surfaces.http.channel_routes import get_channel_service
    from coffer.surfaces.http.mcp.dependencies import get_health_repo_optional

    return build_attention_sources(
        resource_svc=resource_svc,
        credential_store=credential_store,
        connection_service=connection_service,
        auto_detect=get_auto_detect_service(),
        sync_service=sync_service,
        channel_service=get_channel_service(),
        health_repo=get_health_repo_optional(),
    )


__all__ = ["build_attention_sources", "lifespan_attention_sources"]
