"""One-click install of a stdio MCP server's missing launcher (spec 001
amendment 2026-07-10). Split from ``capability_routes`` for the size tier."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.application.mcp.runner_install import install_runner, missing_runner
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_resource_service
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.schemas import McpRunnerInstallOut

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.post("/{name}/install-runner", response_model=McpRunnerInstallOut)
async def install_missing_runner(
    name: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> McpRunnerInstallOut:
    """Install the server's missing launcher via its allowlisted Homebrew
    formula (uvx/uv, npx/node, bunx/bun — the launcher fetches the actual MCP
    package itself on first run). 422 when nothing is missing or the runner
    has no unambiguous install. Blocking for up to the brew run's duration."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))
    config = MCPServerConfig.model_validate(resource.config)
    if config.transport.type != "stdio":
        return error_response(  # type: ignore[return-value]
            "MCP_RUNNER_INSTALL_UNSUPPORTED", "not a stdio server"
        )
    runner = missing_runner(config.transport.command)
    if runner is None:
        return error_response(  # type: ignore[return-value]
            "MCP_RUNNER_INSTALL_UNSUPPORTED",
            f"command {config.transport.command!r} already resolves on this machine",
        )
    formula = await asyncio.to_thread(install_runner, runner)
    await audit.record(
        AuditEventType.MCP_RUNNER_INSTALLED.value,
        ref=resource.ref,
        actor=actor,
        details={"runner": runner, "formula": formula},
    )
    return McpRunnerInstallOut(runner=runner, formula=formula)
