"""``/api/v1/custom-tools/{name}/environments`` and a saved tool's test.

Spec mcp-gateway "Keep a custom-tool group's environments in the group" and
"Manage custom tools through REST and the Custom tools page"; design
align-cli-with-ui-and-add-tool-environments D4. Mounted on the custom tools
router, whose prefix and token check they share.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.mcp.custom_tool_environments import CustomToolEnvironments
from coffer.application.mcp.custom_tools import CustomToolService
from coffer.domain.errors import ConfigValidationError
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.mcp.custom_tool_dependencies import (
    get_custom_tool_environments,
    get_custom_tool_service,
)
from coffer.surfaces.http.mcp.custom_tool_schemas import (
    CustomToolEnvironmentIn,
    CustomToolEnvironmentPatch,
    CustomToolGroupOut,
    CustomToolSavedTestIn,
    CustomToolTestOut,
)
from coffer.surfaces.http.mcp.custom_tool_test_out import test_out
from coffer.surfaces.http.mcp.custom_tool_views_out import group_out

router = APIRouter()

_envs = Depends(get_custom_tool_environments)
_service = Depends(get_custom_tool_service)
_actor = Depends(get_actor)


@router.post("/{name}/environments", response_model=CustomToolGroupOut, status_code=201)
async def add_environment(
    name: str,
    body: CustomToolEnvironmentIn,
    envs: CustomToolEnvironments = _envs,
    actor: str = _actor,
) -> CustomToolGroupOut:
    return group_out(await envs.add(name, body.model_dump(mode="json"), actor=actor))


@router.patch("/{name}/environments/{environment}", response_model=CustomToolGroupOut)
async def update_environment(
    name: str,
    environment: str,
    body: CustomToolEnvironmentPatch,
    envs: CustomToolEnvironments = _envs,
    actor: str = _actor,
) -> CustomToolGroupOut:
    changes: dict[str, Any] = body.model_dump(mode="json", exclude_unset=True)
    for field in ("name", "enabled", "base_url", "headers", "variables", "description"):
        if field in changes and changes[field] is None:
            raise ConfigValidationError(f"{field} cannot be cleared")
    return group_out(await envs.update(name, environment, changes, actor=actor))


@router.delete("/{name}/environments/{environment}", response_model=CustomToolGroupOut)
async def delete_environment(
    name: str, environment: str, envs: CustomToolEnvironments = _envs, actor: str = _actor
) -> CustomToolGroupOut:
    return group_out(await envs.delete(name, environment, actor=actor))


@router.post("/{name}/tools/{tool}/test", response_model=CustomToolTestOut)
async def test_saved_tool(
    name: str, tool: str, body: CustomToolSavedTestIn, svc: CustomToolService = _service
) -> CustomToolTestOut:
    """Run a saved tool once in one environment; saves nothing, logs no invocation."""
    group, transport = await svc.group(name)
    saved = transport.tool(tool)
    outcome = await svc.test_saved(name, tool, body.arguments, body.environment)
    return test_out(outcome, group=group.name, method=saved.method if saved else "GET")
