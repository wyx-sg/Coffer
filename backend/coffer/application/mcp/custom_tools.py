"""Custom-tool groups: create, read, change and delete groups and their tools.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools", "Switch off one
custom tool", "Wait for approval before a custom tool sends its
secret" and "Manage custom tools through REST and the Custom tools page"; design
add-http-custom-tools §2, §5, §9.

A group is an ``mcp_server`` resource of the ``http_api`` transport, so every
write goes through :class:`ResourceService` — the kind's validation, the
missing-secret probe, audit and the eviction of live connections come with
it. OpenAPI import and re-import are in ``custom_tool_import``; the page's
read model in ``custom_tool_views``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from coffer.application.audit_service import AuditService
from coffer.application.mcp.custom_tool_ports import (
    CustomToolRunnerPort,
    ToolTestOutcome,
)
from coffer.application.mcp.custom_tool_secrets import env_secret_resolver
from coffer.application.mcp.custom_tool_views import GroupView, GroupViewer
from coffer.application.mcp.gateway_tool_gate import http_api_transport
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.errors import ConfigValidationError, ScopeInvalidError
from coffer.domain.mcp.custom_tool_errors import (
    CustomToolExists,
    CustomToolNotFound,
    NotACustomToolGroup,
)
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import (
    ENVIRONMENT_ARG,
    LIFTED_ENVIRONMENT,
    select_environment,
)
from coffer.domain.mcp.http_api_render import ArgumentsInvalid
from coffer.domain.mcp.json_schema import validate
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope, validate_scope
from coffer.domain.secrets import is_valid_secret_name, secret_ref, standalone_name

KIND = "mcp_server"
#: Sentinel for "leave this field as it is" in a partial update.
UNSET: Any = object()


def secret_name_of(ref: str) -> str:
    """The Secrets-page name a header's secret ref points at."""
    return standalone_name(ref) or ref


def split_headers(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Header rows ``{name, value | secret [, scheme]}`` -> ``(plain headers,
    secret_refs, auth_schemes)``.

    A row carries a value or a secret, never both. A secret holds the credential
    alone; the row's scheme, if any, is sent in front of it (``Bearer <key>``)."""
    plain: dict[str, str] = {}
    refs: dict[str, str] = {}
    schemes: dict[str, str] = {}
    for row in rows:
        name, value, secret = row["name"], row.get("value"), row.get("secret")
        if value is not None and secret is not None:
            raise ConfigValidationError(f"header {name!r} has a value and a secret")
        if secret is not None:
            if not is_valid_secret_name(secret):
                raise ConfigValidationError(f"{secret!r} is not a secret name")
            refs[name] = secret_ref(secret)
            if row.get("scheme"):
                schemes[name] = row["scheme"]
        else:
            plain[name] = value or ""
    return plain, refs, schemes


def environment_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """An environment as a request writes it (header ROWS) -> its stored fields."""
    plain, refs, schemes = split_headers(list(raw.get("headers") or []))
    out = {k: v for k, v in raw.items() if k != "headers"}
    out.update(headers=plain, secret_refs=refs, auth_schemes=schemes)
    return out


def _validated(fields: dict[str, Any]) -> HttpApiTransport:
    try:
        return HttpApiTransport.model_validate({**fields, "type": "http_api"})
    except ValidationError as e:
        raise ConfigValidationError(str(e)) from e


def validated_tool(raw: dict[str, Any]) -> HttpApiTool:
    try:
        return HttpApiTool.model_validate(raw)
    except ValidationError as e:
        raise ConfigValidationError(str(e)) from e


class CustomToolService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        viewer: GroupViewer,
        resolver: Callable[[], SecretResolver],
        runner: CustomToolRunnerPort,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._resources = resources
        self._audit = audit
        self._viewer = viewer
        self._resolver = resolver
        self._runner = runner
        self._clock = clock

    # --- reading -----------------------------------------------------------

    async def group(self, name: str) -> tuple[Resource, HttpApiTransport]:
        resource = await self._resources.get_by_name(KIND, name)
        transport = http_api_transport(resource)
        if transport is None:
            raise NotACustomToolGroup(name)
        return resource, transport

    async def list_groups(self) -> list[GroupView]:
        rows = await self._resources.list(kind=KIND)
        groups = [(r, t) for r in rows if (t := http_api_transport(r)) is not None]
        return await self._viewer.views(groups)

    async def view(self, name: str) -> GroupView:
        return (await self._viewer.views([await self.group(name)]))[0]

    # --- groups ------------------------------------------------------------

    async def create_group(
        self,
        *,
        name: str,
        description: str | None,
        environments: list[dict[str, Any]],
        timeout_seconds: int,
        agents: list[str] | None,
        tools: list[dict[str, Any]],
        source: dict[str, Any] | None,
        actor: str,
    ) -> GroupView:
        """Create a group. ``environments`` are request-shaped (header rows)."""
        scope = Scope(agents=agents) if agents is not None else None
        try:
            # Refuse before registering, so a bad reach leaves no group behind.
            validate_scope(scope, supports_scope=True)
        except ValueError as e:
            raise ScopeInvalidError(str(e)) from e
        fields: dict[str, Any] = {
            "environments": [environment_fields(e) for e in environments],
            "timeout_seconds": timeout_seconds,
            "tools": tools,
            "source": source,
        }
        transport = _validated(fields)
        config = MCPServerConfig(transport=transport).model_dump(mode="json")
        created = await self._resources.register(KIND, name, config, actor, description)
        if scope is not None:
            await self._resources.update_scope(created.uid, scope, actor=actor)
        return await self.view(name)

    async def update_group(
        self,
        name: str,
        *,
        actor: str,
        description: Any = UNSET,
        base_url: Any = UNSET,
        headers: Any = UNSET,
        timeout_seconds: Any = UNSET,
    ) -> GroupView:
        """Change a group. ``base_url`` and ``headers`` change its environment
        when it has exactly one; with several, they are changed per environment."""
        resource, transport = await self.group(name)
        fields = transport.model_dump(mode="json")
        if timeout_seconds is not UNSET:
            fields["timeout_seconds"] = timeout_seconds
        if base_url is not UNSET or headers is not UNSET:
            if len(transport.environments) != 1:
                raise ConfigValidationError(
                    "this group has several environments; change base_url and headers "
                    "on one environment instead"
                )
            env = fields["environments"][0]
            if base_url is not UNSET:
                env["base_url"] = base_url
            if headers is not UNSET:
                env["headers"], env["secret_refs"], env["auth_schemes"] = split_headers(headers)
        await self._write(resource, _validated(fields), actor, description=description)
        return await self.view(name)

    async def delete_group(self, name: str, *, actor: str) -> None:
        resource, _ = await self.group(name)
        await self._resources.delete(resource.uid, actor=actor)

    # --- tools -------------------------------------------------------------

    async def add_tool(self, name: str, raw: dict[str, Any], *, actor: str) -> GroupView:
        resource, transport = await self.group(name)
        tool = validated_tool(raw)
        if transport.tool(tool.name) is not None:
            raise CustomToolExists(name, tool.name)
        await self._write(
            resource, transport.model_copy(update={"tools": [*transport.tools, tool]}), actor
        )
        return await self.view(name)

    async def update_tool(
        self, name: str, tool_name: str, changes: dict[str, Any], *, actor: str
    ) -> GroupView:
        resource, transport = await self.group(name)
        current = transport.tool(tool_name)
        if current is None:
            raise CustomToolNotFound(name, tool_name)
        merged = validated_tool({**current.model_dump(mode="json"), **changes})
        if merged.name != tool_name and transport.tool(merged.name) is not None:
            raise CustomToolExists(name, merged.name)
        tools = [merged if t.name == tool_name else t for t in transport.tools]
        await self._write(resource, transport.model_copy(update={"tools": tools}), actor)
        return await self.view(name)

    async def delete_tool(self, name: str, tool_name: str, *, actor: str) -> GroupView:
        resource, transport = await self.group(name)
        if transport.tool(tool_name) is None:
            raise CustomToolNotFound(name, tool_name)
        tools = [t for t in transport.tools if t.name != tool_name]
        await self._write(resource, transport.model_copy(update={"tools": tools}), actor)
        return await self.view(name)

    async def test_tool(
        self,
        name: str,
        raw_tool: dict[str, Any],
        arguments: dict[str, Any],
        environment: str | None = None,
    ) -> ToolTestOutcome:
        """Run a draft tool once in one of the group's environments.

        Nothing is saved and nothing enters the invocation log (spec
        mcp-gateway "Manage custom tools through REST and the Custom tools page"); the
        secret goes through the same boundary as a call does.
        """
        resource, transport = await self.group(name)
        return await self._run(
            resource, transport, validated_tool(raw_tool), arguments, environment
        )

    async def test_saved(
        self, name: str, tool_name: str, arguments: dict[str, Any], environment: str | None
    ) -> ToolTestOutcome:
        """Run a saved tool once in one of the group's environments."""
        resource, transport = await self.group(name)
        tool = transport.tool(tool_name)
        if tool is None:
            raise CustomToolNotFound(name, tool_name)
        return await self._run(resource, transport, tool, arguments, environment)

    async def _run(
        self,
        resource: Resource,
        transport: HttpApiTransport,
        tool: HttpApiTool,
        arguments: dict[str, Any],
        environment: str | None,
    ) -> ToolTestOutcome:
        """The checks a call makes, in its order, then one request: the
        environment, the arguments against the schema, then the environment's
        secrets — each refused before anything is sent."""
        chosen = dict(arguments)
        if environment is not None:
            chosen[ENVIRONMENT_ARG] = environment
        env, args = select_environment(transport.environments, resource.name, chosen)
        errors = validate(tool.input_schema, args)
        if errors:
            raise ArgumentsInvalid(errors)
        overlay = await env_secret_resolver(self._resolver(), resource)(env)
        outcome = await self._runner.run(transport, env, tool, args, overlay)
        return replace(outcome, environment=env.name)

    async def test_unsaved(
        self,
        *,
        base_url: str,
        headers: list[dict[str, Any]],
        timeout_seconds: int,
        raw_tool: dict[str, Any],
        arguments: dict[str, Any],
        variables: dict[str, str] | None = None,
    ) -> ToolTestOutcome:
        """Run a request of a group that is not saved yet (spec mcp-gateway
        "Test a custom tool request before its group is saved").

        The group has no approved secret binding, so no secret is sent; its
        base URL was typed into a form, so the runner checks it against the
        SSRF guard. Nothing is saved or logged.
        """
        # A secret header is left out: an unsaved group has no approved binding.
        plain, _, _ = split_headers(headers)
        tool = validated_tool(raw_tool)
        env = {
            "name": LIFTED_ENVIRONMENT,
            "base_url": base_url,
            "headers": plain,
            "variables": variables or {},
        }
        transport = _validated(
            {"environments": [env], "timeout_seconds": timeout_seconds, "tools": [tool]}
        )
        args = {k: v for k, v in arguments.items() if k != ENVIRONMENT_ARG}
        errors = validate(tool.input_schema, args)
        if errors:
            raise ArgumentsInvalid(errors)
        return await self._runner.run_unsaved(transport, transport.environments[0], tool, args)

    # --- the one write path ----------------------------------------------------

    async def _write(
        self,
        resource: Resource,
        transport: HttpApiTransport,
        actor: str,
        *,
        description: Any = UNSET,
    ) -> Resource:
        config = MCPServerConfig.model_validate(resource.config).model_copy(
            update={"transport": _validated(transport.model_dump(mode="json"))}
        )
        return await self._resources.update_config(
            resource.uid,
            config.model_dump(mode="json"),
            actor,
            description=resource.description if description is UNSET else description,
        )

    async def write_transport(
        self, resource: Resource, transport: HttpApiTransport, actor: str
    ) -> Resource:
        """For ``custom_tool_import``: the same write path."""
        return await self._write(resource, transport, actor)

    def validated(self, fields: dict[str, Any]) -> HttpApiTransport:
        """For ``custom_tool_environments``: a group's fields, validated."""
        return _validated(fields)

    def now(self) -> datetime:
        return self._clock()


__all__ = [
    "UNSET",
    "CustomToolService",
    "environment_fields",
    "secret_name_of",
    "split_headers",
    "validated_tool",
]
