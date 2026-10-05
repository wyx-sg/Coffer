"""Add, change, rename, switch and delete a custom-tool group's environments.

Spec mcp-gateway "Keep a custom-tool group's environments in the group"; design
align-cli-with-ui-and-add-tool-environments D4. Every change is a write of the
whole group through ``CustomToolService``'s one write path, so validation, the
missing-secret probe, audit, the secret boundary's post-register seam (which
asks for approval of a moved or new environment's secrets) and the eviction of
live connections come with it. A rename keeps the environment's binding key, so
its approvals survive; a new environment's key is its first name.
"""

from __future__ import annotations

from typing import Any

from coffer.application.mcp.custom_tool_views import GroupView
from coffer.application.mcp.custom_tools import (
    CustomToolService,
    environment_fields,
    split_headers,
)
from coffer.domain.errors import ConfigValidationError
from coffer.domain.mcp.custom_tool_env_errors import (
    CustomToolEnvironmentExists,
    CustomToolEnvironmentNotFound,
    CustomToolLastEnvironment,
)
from coffer.domain.mcp.http_api import HttpApiTransport

#: Fields of an environment a change may set; ``headers`` replaces every row.
_CHANGEABLE = (
    "name",
    "description",
    "enabled",
    "base_url",
    "headers",
    "variables",
    "timeout_seconds",
)


class CustomToolEnvironments:
    def __init__(self, service: CustomToolService) -> None:
        self._service = service

    async def add(self, group: str, raw: dict[str, Any], *, actor: str) -> GroupView:
        resource, transport = await self._service.group(group)
        name = str(raw.get("name", ""))
        if _find(transport, name) is not None:
            raise CustomToolEnvironmentExists(group, name)
        fields = transport.model_dump(mode="json")
        taken = {e.key for e in transport.environments}
        env = environment_fields({k: v for k, v in raw.items() if k != "key"})
        # The binding key is the first name; a name once used and renamed away
        # keeps its key, so a new environment reusing it gets a fresh one.
        env["key"] = _fresh_key(name, taken)
        fields["environments"].append(env)
        await self._service.write_transport(resource, self._service.validated(fields), actor)
        return await self._service.view(group)

    async def update(
        self, group: str, name: str, changes: dict[str, Any], *, actor: str
    ) -> GroupView:
        resource, transport = await self._service.group(group)
        if _find(transport, name) is None:
            raise CustomToolEnvironmentNotFound(group, name)
        unknown = sorted(set(changes) - set(_CHANGEABLE))
        if unknown:
            raise ConfigValidationError("unknown environment field(s): " + ", ".join(unknown))
        new_name = changes.get("name")
        if new_name and new_name != name and _find(transport, new_name) is not None:
            raise CustomToolEnvironmentExists(group, new_name)
        fields = transport.model_dump(mode="json")
        for env in fields["environments"]:
            if env["name"] != name:
                continue
            for key, value in changes.items():
                if key == "headers":
                    env["headers"], env["secret_refs"], env["auth_schemes"] = split_headers(
                        list(value or [])
                    )
                else:
                    env[key] = value
        await self._service.write_transport(resource, self._service.validated(fields), actor)
        return await self._service.view(group)

    async def delete(self, group: str, name: str, *, actor: str) -> GroupView:
        resource, transport = await self._service.group(group)
        if _find(transport, name) is None:
            raise CustomToolEnvironmentNotFound(group, name)
        if len(transport.environments) == 1:
            raise CustomToolLastEnvironment(group)
        fields = transport.model_dump(mode="json")
        fields["environments"] = [e for e in fields["environments"] if e["name"] != name]
        await self._service.write_transport(resource, self._service.validated(fields), actor)
        return await self._service.view(group)


def _find(transport: HttpApiTransport, name: str) -> object | None:
    return next((e for e in transport.environments if e.name.lower() == name.lower()), None)


def _fresh_key(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    n = 2
    while f"{name}-{n}"[:40] in taken:
        n += 1
    return f"{name}-{n}"[:40]


__all__ = ["CustomToolEnvironments", "environment_fields"]
