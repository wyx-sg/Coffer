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

from collections.abc import Callable

from coffer.application.agent.attention import AgentAttentionSource
from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.connection_service import AgentConnectionService
from coffer.application.attention import AttentionSource
from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.channel.service import ChannelService
from coffer.application.mcp.attention import McpAttentionSource
from coffer.application.resource_service import ResourceService
from coffer.application.secret.attention import SecretAttentionSource
from coffer.application.skill.cli_attention import CliAttentionSource
from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.application.sync.attention import SyncAttentionSource
from coffer.application.sync.service import SyncService
from coffer.infrastructure.mcp.health_repo import MCPServerHealthRepo
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.surfaces.http.channel_handoff import sdk_missing_handoff
from coffer.surfaces.http.mcp.handoff_views import McpHandoffs


def build_attention_sources(
    *,
    resource_svc: ResourceService,
    secret_store: EncryptedSecretStore,
    connection_service: AgentConnectionService,
    auto_detect: AutoDetectService,
    sync_service: SyncService | None,
    channel_service: ChannelService | None,
    health_repo: MCPServerHealthRepo | None,
    cli_service: CliRequirementService | None = None,
    protections_on: Callable[[], bool] | None = None,
) -> list[AttentionSource]:
    """Every kind's source, in the order the Overview groups them."""
    sources: list[AttentionSource] = []
    if health_repo is not None:
        sources.append(
            McpAttentionSource(
                resources=resource_svc,
                health=health_repo,
                secrets=secret_store,
                handoffs=McpHandoffs(),
            )
        )
    sources.append(
        AgentAttentionSource(agents=resource_svc, detect=auto_detect, connection=connection_service)
    )
    if channel_service is not None:
        sources.append(
            ChannelAttentionSource(
                resources=resource_svc, channels=channel_service, sdk_handoff=sdk_missing_handoff
            )
        )
    if sync_service is not None:
        sources.append(SyncAttentionSource(sync=sync_service))
    if cli_service is not None:
        sources.append(CliAttentionSource(cli_service))
    if protections_on is not None:
        sources.append(SecretAttentionSource(protections_on))
    return sources


def lifespan_attention_sources(
    *,
    resource_svc: ResourceService,
    secret_store: EncryptedSecretStore,
    connection_service: AgentConnectionService,
    sync_service: SyncService | None,
) -> list[AttentionSource]:
    """:func:`build_attention_sources` with the services the kinds published
    while they were wired (the channel service, the agent detector, the MCP
    health store) looked up where they were published."""
    from coffer.surfaces.http.agent_dependencies import get_auto_detect_service
    from coffer.surfaces.http.channel_routes import get_channel_service
    from coffer.surfaces.http.cli_dependencies import get_cli_requirement_service_optional
    from coffer.surfaces.http.mcp.dependencies import get_health_repo_optional
    from coffer.surfaces.http.secret_boundary_wiring import get_secret_boundary

    return build_attention_sources(
        resource_svc=resource_svc,
        secret_store=secret_store,
        connection_service=connection_service,
        auto_detect=get_auto_detect_service(),
        sync_service=sync_service,
        channel_service=get_channel_service(),
        health_repo=get_health_repo_optional(),
        cli_service=get_cli_requirement_service_optional(),
        protections_on=lambda: get_secret_boundary().protections_on(),
    )


__all__ = ["build_attention_sources", "lifespan_attention_sources"]
